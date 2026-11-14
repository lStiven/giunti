import base64
from typing import Any

import litellm
import pytest
from litellm import exceptions as litellm_errors
from litellm.types.utils import Choices, ModelResponse, Usage
from litellm.types.utils import Message as LiteLLMMessage

from app.core.config import LLMModelConfig
from app.llm.client import (
    TOKENS_PER_IMAGE,
    ImagePart,
    LiteLLMBackend,
    Message,
    TextPart,
    context_window,
    estimate_tokens,
    to_openai_message,
)
from app.llm.errors import FailureKind, ModelCallError

MODEL = LLMModelConfig(id="test", model="gemini/test-model", max_output_tokens=1234)


def _response(content: str | None, finish_reason: str = "stop") -> ModelResponse:
    return ModelResponse(
        choices=[
            Choices(
                finish_reason=finish_reason,
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        usage=Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )


class FakeLiteLLM:
    def __init__(self, result: ModelResponse | Exception) -> None:
        self.result = result
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **request: Any) -> ModelResponse:  # noqa: ANN401 - mirrors LiteLLM
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def backend() -> LiteLLMBackend:
    return LiteLLMBackend(timeout_s=42, api_keys={"gemini": "secret-key"})


def _install(monkeypatch: pytest.MonkeyPatch, result: ModelResponse | Exception) -> FakeLiteLLM:
    fake = FakeLiteLLM(result)
    monkeypatch.setattr(litellm, "acompletion", fake)
    return fake


async def test_answer_text_and_token_usage_are_returned(
    backend: LiteLLMBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _response('{"ok": true}'))

    completion = await backend.complete(MODEL, [Message.text("user", "hi")])

    assert completion.text == '{"ok": true}'
    assert (completion.input_tokens, completion.output_tokens) == (11, 7)


async def test_request_uses_model_options_without_internal_retries(
    backend: LiteLLMBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _install(monkeypatch, _response("{}"))
    model = MODEL.model_copy(update={"temperature": 0.0, "reasoning_effort": "low"})

    await backend.complete(model, [Message.text("user", "hi")])

    request = fake.requests[0]
    assert request["model"] == "gemini/test-model"
    assert request["api_key"] == "secret-key"
    assert request["max_tokens"] == 1234
    assert request["timeout"] == 42
    assert request["num_retries"] == 0
    assert request["temperature"] == 0.0
    assert request["reasoning_effort"] == "low"
    assert request["response_format"] == {"type": "json_object"}


async def test_provider_defaults_are_kept_when_options_are_not_set(
    backend: LiteLLMBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _install(monkeypatch, _response("{}"))
    model = LLMModelConfig(id="unknown", model="unknown/model", json_mode=True)

    await backend.complete(model, [Message.text("user", "hi")])

    request = fake.requests[0]
    assert "temperature" not in request
    assert "reasoning_effort" not in request
    assert "api_key" not in request
    assert "response_format" not in request


async def test_output_limit_reached_is_truncated(
    backend: LiteLLMBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _response('{"items": [', finish_reason="length"))

    with pytest.raises(ModelCallError) as error:
        await backend.complete(MODEL, [Message.text("user", "hi")])

    assert error.value.kind is FailureKind.TRUNCATED


@pytest.mark.parametrize(
    ("content", "finish_reason"), [("partial", "content_filter"), ("", "stop"), (None, "stop")]
)
async def test_blocked_or_empty_answer_is_refused(
    backend: LiteLLMBackend,
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
    finish_reason: str,
) -> None:
    _install(monkeypatch, _response(content, finish_reason=finish_reason))

    with pytest.raises(ModelCallError) as error:
        await backend.complete(MODEL, [Message.text("user", "hi")])

    assert error.value.kind is FailureKind.REFUSED


async def test_provider_exceptions_are_classified(
    backend: LiteLLMBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, litellm_errors.AuthenticationError("bad key", "gemini", MODEL.model))

    with pytest.raises(ModelCallError) as error:
        await backend.complete(MODEL, [Message.text("user", "hi")])

    assert error.value.kind is FailureKind.CONFIGURATION


def test_text_only_message_is_sent_as_plain_text() -> None:
    message = Message("user", (TextPart("a"), TextPart("b")))

    assert to_openai_message(message) == {"role": "user", "content": "a\n\nb"}


def test_images_are_sent_as_png_data_urls_in_order() -> None:
    message = Message("user", (TextPart("page 1"), ImagePart(b"\x89PNG")))

    converted = to_openai_message(message)

    encoded = base64.b64encode(b"\x89PNG").decode()
    assert converted["content"] == [
        {"type": "text", "text": "page 1"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
    ]


def test_configured_context_window_takes_precedence() -> None:
    model = LLMModelConfig(id="test", model="gemini/test-model", max_input_tokens=1000)

    assert context_window(model) == 1000


def test_unknown_model_has_no_known_context_window() -> None:
    assert context_window(LLMModelConfig(id="unknown", model="unknown/model")) is None


def test_token_estimate_counts_text_and_images() -> None:
    messages = [Message("user", (TextPart("x" * 300), ImagePart(b"png")))]

    assert estimate_tokens(messages) == 100 + TOKENS_PER_IMAGE
