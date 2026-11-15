from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel

from app.core.config import LLMCatalog, LLMModelConfig, ProviderInfo
from app.core.errors import AppError, ErrorCode
from app.llm.circuit_breaker import BreakerRegistry
from app.llm.client import Completion, ContentPart, ImagePart, Message, TextPart
from app.llm.errors import FailureKind, LLMRunError, ModelCallError
from app.llm.structured import (
    MAX_REPORTED_ERRORS,
    ExtractionTask,
    StructuredRunner,
    extract_json_object,
    parse_output,
)

FLASH = LLMModelConfig(id="flash", model="gemini/flash")
OTHER = LLMModelConfig(id="other", model="other/model")
TEXT_ONLY = LLMModelConfig(id="text-only", model="other/text-only", vision=False)
TUNABLE = LLMModelConfig(
    id="tunable", model="gemini/tunable", reasoning_effort="high", fast_reasoning_effort="low"
)

type Script = list[Completion | ModelCallError]


class Answer(BaseModel):
    title: str
    count: int


def _even_count(answer: Answer) -> Sequence[str]:
    return [] if answer.count % 2 == 0 else [f"count: {answer.count} must be even"]


def _title_is_ok(answer: Answer) -> Sequence[str]:
    return [] if answer.title == "ok" else [f"title: '{answer.title}' is not in the document"]


TASK = ExtractionTask(
    name="test",
    output_type=Answer,
    instructions="Return JSON.",
    validate=_even_count,
    review=_title_is_ok,
)
CONTENT: list[ContentPart] = [TextPart("document text")]
VALID = Completion('{"title": "ok", "count": 2}', input_tokens=10, output_tokens=5)
DOUBTFUL = Completion('{"title": "maybe", "count": 2}')


@dataclass
class FakeBackend:
    scripts: dict[str, Script]
    calls: list[tuple[str, list[Message]]] = field(default_factory=list)
    efforts: list[str | None] = field(default_factory=list)

    async def complete(self, model: LLMModelConfig, messages: Sequence[Message]) -> Completion:
        self.calls.append((model.id, list(messages)))
        self.efforts.append(model.reasoning_effort)
        result = self.scripts[model.id].pop(0)
        if isinstance(result, ModelCallError):
            raise result
        return result

    def models_called(self) -> list[str]:
        return [model for model, _ in self.calls]


@dataclass
class FakeSleep:
    delays: list[float] = field(default_factory=list)

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _catalog(models: Sequence[LLMModelConfig]) -> LLMCatalog:
    providers = {
        model.provider: ProviderInfo(label=model.provider, description="") for model in models
    }
    default_model = models[0].id if models else ""
    return LLMCatalog(default_model=default_model, providers=providers, models=list(models))


def _runner(  # noqa: PLR0913 - test helper with optional collaborators
    backend: FakeBackend,
    models: Sequence[LLMModelConfig] = (FLASH, OTHER),
    *,
    sleep: FakeSleep | None = None,
    breakers: BreakerRegistry | None = None,
    window: int | None = None,
    disabled: Sequence[str] = (),
) -> StructuredRunner:
    return StructuredRunner(
        _catalog(models),
        backend,
        max_retries=2,
        repair_attempts=1,
        disabled_model_ids=disabled,
        breakers=breakers,
        sleep=sleep or FakeSleep(),
        window_of=lambda _: window,
    )


def _error(kind: FailureKind, retry_after_s: float | None = None) -> ModelCallError:
    return ModelCallError(kind, f"{kind} detail", retry_after_s=retry_after_s)


async def test_default_model_is_used_when_none_is_chosen() -> None:
    backend = FakeBackend({FLASH.id: [VALID]})

    result = await _runner(backend).run(TASK, CONTENT)

    assert result.value == Answer(title="ok", count=2)
    assert result.model_id == FLASH.id
    assert result.warnings == ()
    assert (result.input_tokens, result.output_tokens) == (10, 5)


async def test_chosen_model_is_used() -> None:
    backend = FakeBackend({OTHER.id: [VALID]})

    result = await _runner(backend).run(TASK, CONTENT, model_id=OTHER.id)

    assert result.model_id == OTHER.id
    assert backend.models_called() == [OTHER.id]


async def test_each_mode_uses_its_reasoning_effort() -> None:
    backend = FakeBackend({TUNABLE.id: [VALID, VALID]})
    runner = _runner(backend, (TUNABLE,))

    await runner.run(TASK, CONTENT, mode="fast")
    await runner.run(TASK, CONTENT, mode="precise")

    assert backend.efforts == ["low", "high"]


async def test_the_catalog_default_mode_applies_when_the_request_has_none() -> None:
    backend = FakeBackend({TUNABLE.id: [VALID]})
    catalog = _catalog((TUNABLE,)).model_copy(update={"default_mode": "fast"})
    runner = StructuredRunner(catalog, backend, max_retries=0, repair_attempts=0)

    await runner.run(TASK, CONTENT)

    assert backend.efforts == ["low"]


async def test_models_without_a_fast_mode_run_in_precise_mode() -> None:
    backend = FakeBackend({FLASH.id: [VALID]})
    runner = _runner(backend)

    await runner.run(TASK, CONTENT, mode="fast")

    assert runner.resolve_mode(FLASH, "fast") == "precise"
    assert backend.efforts == [None]


async def test_request_has_instructions_as_system_and_content_as_user() -> None:
    backend = FakeBackend({FLASH.id: [VALID]})

    await _runner(backend).run(TASK, CONTENT)

    assert backend.calls[0][1] == [
        Message.text("system", "Return JSON."),
        Message("user", tuple(CONTENT)),
    ]


async def test_transient_errors_are_retried_with_backoff() -> None:
    sleep = FakeSleep()
    backend = FakeBackend(
        {FLASH.id: [_error(FailureKind.TRANSIENT), _error(FailureKind.TRANSIENT), VALID]}
    )

    result = await _runner(backend, sleep=sleep).run(TASK, CONTENT)

    assert result.model_id == FLASH.id
    assert len(sleep.delays) == 2
    assert 1 <= sleep.delays[0] <= 2
    assert 2 <= sleep.delays[1] <= 4


async def test_provider_requested_delay_is_respected() -> None:
    sleep = FakeSleep()
    backend = FakeBackend({FLASH.id: [_error(FailureKind.TRANSIENT, 12), VALID]})

    await _runner(backend, sleep=sleep).run(TASK, CONTENT)

    assert sleep.delays == [12]


async def test_too_long_requested_delay_fails_without_waiting() -> None:
    sleep = FakeSleep()
    backend = FakeBackend({FLASH.id: [_error(FailureKind.TRANSIENT, 3600)]})

    with pytest.raises(LLMRunError) as error:
        await _runner(backend, sleep=sleep).run(TASK, CONTENT)

    assert error.value.code is ErrorCode.LLM_UNAVAILABLE
    assert sleep.delays == []


async def test_failure_never_falls_back_to_another_model() -> None:
    backend = FakeBackend({FLASH.id: [_error(FailureKind.TRANSIENT)] * 3, OTHER.id: [VALID]})

    with pytest.raises(LLMRunError) as error:
        await _runner(backend).run(TASK, CONTENT)

    assert error.value.kind is FailureKind.TRANSIENT
    assert backend.models_called() == [FLASH.id] * 3


@pytest.mark.parametrize(
    ("kind", "code", "text"),
    [
        (FailureKind.QUOTA_EXHAUSTED, ErrorCode.LLM_UNAVAILABLE, "quota"),
        (FailureKind.CONFIGURATION, ErrorCode.LLM_UNAVAILABLE, "not correctly configured"),
        (FailureKind.REFUSED, ErrorCode.INVALID_LLM_RESPONSE, "refused"),
        (FailureKind.TRUNCATED, ErrorCode.INVALID_LLM_RESPONSE, "cut off"),
        (FailureKind.CONTEXT_EXCEEDED, ErrorCode.INVALID_REQUEST, "too long"),
    ],
)
async def test_non_transient_failures_are_reported_without_retrying(
    kind: FailureKind, code: ErrorCode, text: str
) -> None:
    backend = FakeBackend({FLASH.id: [_error(kind)]})

    with pytest.raises(LLMRunError) as error:
        await _runner(backend).run(TASK, CONTENT)

    assert error.value.code is code
    assert text in error.value.message
    assert "'flash'" in error.value.message
    assert backend.models_called() == [FLASH.id]


async def test_invalid_json_is_repaired_with_the_concrete_errors() -> None:
    backend = FakeBackend({FLASH.id: [Completion('{"title": "ok"}'), VALID]})

    result = await _runner(backend).run(TASK, CONTENT)

    assert result.repairs == 1
    repair_messages = backend.calls[1][1]
    assert repair_messages[-2] == Message.text("assistant", '{"title": "ok"}')
    assert "count: Field required" in _text(repair_messages[-1])


async def test_rule_violations_are_sent_back_for_repair() -> None:
    backend = FakeBackend({FLASH.id: [Completion('{"title": "ok", "count": 3}'), VALID]})

    await _runner(backend).run(TASK, CONTENT)

    assert "count: 3 must be even" in _text(backend.calls[1][1][-1])


async def test_output_still_breaking_rules_after_repairs_fails() -> None:
    invalid = Completion("not json at all")
    backend = FakeBackend({FLASH.id: [invalid, invalid]})

    with pytest.raises(LLMRunError) as error:
        await _runner(backend).run(TASK, CONTENT)

    assert error.value.code is ErrorCode.INVALID_LLM_RESPONSE
    assert error.value.kind is FailureKind.INVALID_OUTPUT


async def test_review_issues_are_sent_back_and_resolved() -> None:
    backend = FakeBackend({FLASH.id: [DOUBTFUL, VALID]})

    result = await _runner(backend).run(TASK, CONTENT)

    assert result.value.title == "ok"
    assert result.warnings == ()
    assert "title: 'maybe' is not in the document" in _text(backend.calls[1][1][-1])


async def test_persistent_review_issues_become_warnings() -> None:
    backend = FakeBackend({FLASH.id: [DOUBTFUL, DOUBTFUL]})

    result = await _runner(backend).run(TASK, CONTENT)

    assert result.value.title == "maybe"
    assert result.warnings == ("title: 'maybe' is not in the document",)


async def test_valid_answer_is_kept_when_the_repair_breaks_the_rules() -> None:
    backend = FakeBackend({FLASH.id: [DOUBTFUL, Completion("broken")]})

    result = await _runner(backend).run(TASK, CONTENT)

    assert result.value.title == "maybe"
    assert result.warnings == ("title: 'maybe' is not in the document",)


async def test_no_enabled_models_fails_with_no_models_available() -> None:
    with pytest.raises(AppError) as error:
        await _runner(FakeBackend({}), models=()).run(TASK, CONTENT)

    assert error.value.code is ErrorCode.NO_MODELS_AVAILABLE
    assert "API key" in error.value.message


async def test_model_without_api_key_fails_with_invalid_request() -> None:
    with pytest.raises(AppError) as error:
        await _runner(FakeBackend({}), disabled=["groq-qwen"]).run(
            TASK, CONTENT, model_id="groq-qwen"
        )

    assert error.value.code is ErrorCode.INVALID_REQUEST
    assert "no API key" in error.value.message


async def test_unknown_model_fails_with_invalid_request() -> None:
    with pytest.raises(AppError) as error:
        await _runner(FakeBackend({})).run(TASK, CONTENT, model_id="does-not-exist")

    assert error.value.code is ErrorCode.INVALID_REQUEST
    assert "Unknown model 'does-not-exist'" in error.value.message


async def test_model_without_vision_for_required_images_fails_with_invalid_request() -> None:
    content: list[ContentPart] = [TextPart("scan"), ImagePart(b"png", required=True)]

    with pytest.raises(AppError) as error:
        await _runner(FakeBackend({}), models=(TEXT_ONLY,)).run(TASK, content)

    assert error.value.code is ErrorCode.INVALID_REQUEST
    assert "cannot read images" in error.value.message


async def test_optional_images_are_dropped_for_models_without_vision() -> None:
    backend = FakeBackend({TEXT_ONLY.id: [VALID]})
    content: list[ContentPart] = [TextPart("text"), ImagePart(b"png", required=False)]

    await _runner(backend, models=(TEXT_ONLY,)).run(TASK, content)

    assert backend.calls[0][1][1] == Message("user", (TextPart("text"),))


async def test_document_larger_than_the_context_window_fails_before_calling() -> None:
    backend = FakeBackend({})

    with pytest.raises(AppError) as error:
        await _runner(backend, window=100).run(TASK, [TextPart("x" * 3000)])

    assert error.value.code is ErrorCode.INVALID_REQUEST
    assert backend.calls == []


async def test_exhausted_quota_pauses_the_model() -> None:
    breakers = BreakerRegistry()
    backend = FakeBackend({FLASH.id: [_error(FailureKind.QUOTA_EXHAUSTED)]})
    runner = _runner(backend, breakers=breakers)
    with pytest.raises(LLMRunError):
        await runner.run(TASK, CONTENT)

    with pytest.raises(AppError) as error:
        await runner.run(TASK, CONTENT)

    assert error.value.code is ErrorCode.LLM_UNAVAILABLE
    assert "temporarily unavailable" in error.value.message
    assert backend.models_called() == [FLASH.id]


async def test_repeated_transient_failures_open_the_circuit() -> None:
    breakers = BreakerRegistry()
    backend = FakeBackend({FLASH.id: [_error(FailureKind.TRANSIENT)] * 9})
    runner = _runner(backend, breakers=breakers)

    for _ in range(3):
        with pytest.raises(LLMRunError):
            await runner.run(TASK, CONTENT)

    assert not breakers.get(FLASH.id).is_available()


@pytest.mark.parametrize(
    "text",
    [
        '{"title": "ok", "count": 2}',
        '```json\n{"title": "ok", "count": 2}\n```',
        'Here is the result:\n{"title": "ok", "count": 2}\nHope it helps.',
    ],
)
def test_json_is_found_inside_fences_or_prose(text: str) -> None:
    assert parse_output(TASK, text).value == Answer(title="ok", count=2)


def test_answer_without_json_object_is_reported() -> None:
    assert extract_json_object("no braces here") is None
    assert parse_output(TASK, "no braces").errors == ("The answer does not contain a JSON object.",)


def test_malformed_json_reports_its_position() -> None:
    errors = parse_output(TASK, '{"title": "ok",, "count": 2}').errors

    assert errors[0].startswith("Invalid JSON at line 1, column 16")


def test_validation_errors_show_paths_but_not_rejected_values() -> None:
    errors = parse_output(TASK, '{"title": "SECRET TEXT", "count": "many"}').errors

    assert errors == (
        "count: Input should be a valid integer, unable to parse string as an integer",
    )


def test_too_many_validation_errors_are_summarised() -> None:
    class Many(BaseModel):
        values: list[int]

    task = ExtractionTask(name="many", output_type=Many, instructions="")
    text = '{"values": [' + ", ".join(['"x"'] * 40) + "]}"

    errors = parse_output(task, text).errors

    assert len(errors) == MAX_REPORTED_ERRORS + 1
    assert errors[0].startswith("values[0]: ")
    assert errors[-1] == "... and 10 more errors."


def _text(message: Message) -> str:
    return "".join(part.text for part in message.parts if isinstance(part, TextPart))
