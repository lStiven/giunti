"""Problem-agnostic structured output on one chosen model.

`ExtractionTask[T]` bundles a Pydantic schema, instructions and two kinds of checks:

- `validate`: hard rules. A result breaking them is never returned.
- `review`: soft checks (for example, grounding against the source). They are sent back to the
  model once, and if they persist the result is returned with them as warnings.

`StructuredRunner.run(task, content, model_id=...)` uses only the chosen model (or the catalog
default): there is no fallback, so clients can compare models. On that model it retries
transient failures with exponential backoff and asks it to fix concrete errors
(`repair_attempts` times). Only models whose provider has an API key are enabled.

JSON is requested in the instructions instead of each provider's native structured output so
every provider behaves the same.
"""

import asyncio
import json
import logging
import math
import random
import time
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from app.core.config import LLMCatalog, LLMModelConfig, Settings
from app.core.errors import AppError, ErrorCode, ErrorReason
from app.llm.circuit_breaker import BreakerRegistry
from app.llm.client import (
    Completion,
    CompletionBackend,
    ContentPart,
    ImagePart,
    LiteLLMBackend,
    Message,
    context_window,
    estimate_tokens,
)
from app.llm.errors import FailureKind, LLMRunError, ModelCallError

BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 30.0
# A provider asking to wait longer than this is reported as unavailable instead of waiting.
MAX_RETRY_WAIT_S = 60.0
QUOTA_PAUSE_S = 15 * 60.0
CONFIGURATION_PAUSE_S = 5 * 60.0
MAX_REPORTED_ERRORS = 30

_FAILURE_REASONS: dict[FailureKind, ErrorReason] = {
    FailureKind.TRANSIENT: ErrorReason.MODEL_NOT_RESPONDING,
    FailureKind.QUOTA_EXHAUSTED: ErrorReason.QUOTA_EXHAUSTED,
    FailureKind.CONFIGURATION: ErrorReason.MODEL_MISCONFIGURED,
    FailureKind.REFUSED: ErrorReason.MODEL_REFUSED,
    FailureKind.TRUNCATED: ErrorReason.OUTPUT_TOO_LONG,
    FailureKind.CONTEXT_EXCEEDED: ErrorReason.DOCUMENT_TOO_LONG_FOR_MODEL,
    FailureKind.INVALID_OUTPUT: ErrorReason.INVALID_OUTPUT,
}

_FAILURE_ERRORS: dict[FailureKind, tuple[ErrorCode, str]] = {
    FailureKind.TRANSIENT: (
        ErrorCode.LLM_UNAVAILABLE,
        (
            "The model '{id}' did not respond after several attempts. "
            "Try again later or choose another model."
        ),
    ),
    FailureKind.QUOTA_EXHAUSTED: (
        ErrorCode.LLM_UNAVAILABLE,
        "The quota of the model '{id}' is exhausted. Choose another model or try again later.",
    ),
    FailureKind.CONFIGURATION: (
        ErrorCode.LLM_UNAVAILABLE,
        "The model '{id}' is not correctly configured on the server. Choose another model.",
    ),
    FailureKind.REFUSED: (
        ErrorCode.INVALID_LLM_RESPONSE,
        "The model '{id}' refused to process the document.",
    ),
    FailureKind.TRUNCATED: (
        ErrorCode.INVALID_LLM_RESPONSE,
        (
            "The answer of the model '{id}' was cut off: the document has more content than "
            "the model can return at once."
        ),
    ),
    FailureKind.CONTEXT_EXCEEDED: (
        ErrorCode.INVALID_REQUEST,
        "The document is too long for the model '{id}'. Choose a model with a larger context.",
    ),
    FailureKind.INVALID_OUTPUT: (
        ErrorCode.INVALID_LLM_RESPONSE,
        "The model '{id}' did not return a valid extraction.",
    ),
}

logger = logging.getLogger(__name__)


def _no_rules(_: BaseModel) -> Sequence[str]:
    return ()


@dataclass(frozen=True, slots=True)
class ExtractionTask[T: BaseModel]:
    """What to extract: the output schema, the instructions and the checks.

    Rule violations and review issues are sent back to the model, so they must be specific
    ("items[3]: the correct answer 'E' is not one of the alternatives").
    """

    name: str
    output_type: type[T]
    instructions: str
    validate: Callable[[T], Sequence[str]] = field(default=_no_rules)
    review: Callable[[T], Sequence[str]] = field(default=_no_rules)


@dataclass(frozen=True, slots=True)
class StructuredResult[T: BaseModel]:
    value: T
    model_id: str
    warnings: tuple[str, ...]
    repairs: int
    input_tokens: int
    output_tokens: int
    duration_ms: int


@dataclass(slots=True)
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    repairs: int = 0


@dataclass(frozen=True, slots=True)
class ParseOutcome[T: BaseModel]:
    value: T | None
    errors: tuple[str, ...]


class StructuredRunner:
    def __init__(  # noqa: PLR0913 - every collaborator is injectable for tests
        self,
        catalog: LLMCatalog,
        backend: CompletionBackend,
        *,
        max_retries: int,
        repair_attempts: int,
        disabled_model_ids: Collection[str] = (),
        breakers: BreakerRegistry | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        window_of: Callable[[LLMModelConfig], int | None] = context_window,
    ) -> None:
        """`catalog` holds only the enabled models; `disabled_model_ids` the ones without key."""
        self._catalog = catalog
        self._disabled_model_ids = frozenset(disabled_model_ids)
        self._backend = backend
        self._max_retries = max_retries
        self._repair_attempts = repair_attempts
        self._breakers = breakers or BreakerRegistry()
        self._sleep = sleep
        self._window_of = window_of

    @classmethod
    def from_settings(cls, settings: Settings) -> "StructuredRunner":
        api_keys = settings.llm_api_keys_by_provider()
        enabled = settings.enabled_llm_catalog()
        enabled_ids = {model.id for model in enabled.models}
        disabled = [
            model.id for model in settings.llm_catalog.models if model.id not in enabled_ids
        ]
        if disabled:
            logger.warning("llm models disabled: no api key", extra={"models": disabled})
        if not enabled.models:
            logger.error("no llm model is enabled: no provider has an api key")
        backend = LiteLLMBackend(timeout_s=settings.llm_timeout_s, api_keys=api_keys)
        return cls(
            enabled,
            backend,
            max_retries=settings.llm_max_retries,
            repair_attempts=settings.llm_repair_attempts,
            disabled_model_ids=disabled,
        )

    async def run[T: BaseModel](
        self,
        task: ExtractionTask[T],
        content: Sequence[ContentPart],
        *,
        model_id: str | None = None,
    ) -> StructuredResult[T]:
        """Runs the task on the chosen model, or on the catalog default when None."""
        model = self.resolve_model(model_id)
        messages = _messages_for(model, task.instructions, content)
        if messages is None:
            message = f"The model '{model.id}' cannot read images, and this document needs it."
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                message,
                reason=ErrorReason.MODEL_CANNOT_READ_IMAGES,
                details={"model": model.id},
            )
        self._check_can_take(model, messages)

        started = time.perf_counter()
        usage = _Usage()
        try:
            value, warnings = await self._run_on_model(task, model, messages, usage)
        except ModelCallError as error:
            self._record_failure(model, error)
            _log_run(task.name, model.id, usage, started, outcome=error.kind, detail=error.detail)
            code, template = _FAILURE_ERRORS[error.kind]
            raise LLMRunError(
                code,
                template.format(id=model.id),
                kind=error.kind,
                reason=_FAILURE_REASONS[error.kind],
                retry_after_s=_suggested_wait(error),
                details={"model": model.id},
            ) from error

        self._breakers.get(model.id).record_success()
        _log_run(task.name, model.id, usage, started, warnings=len(warnings))
        return StructuredResult(
            value=value,
            model_id=model.id,
            warnings=warnings,
            repairs=usage.repairs,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            duration_ms=_ms(started),
        )

    def resolve_model(self, model_id: str | None) -> LLMModelConfig:
        if not self._catalog.models:
            raise AppError(ErrorCode.NO_MODELS_AVAILABLE)
        chosen = model_id or self._catalog.default_model
        model = self._catalog.find(chosen)
        if model is not None:
            return model
        if chosen in self._disabled_model_ids:
            message = (
                f"The model '{chosen}' is not available: its provider has no API key "
                "configured on the server. See GET /api/v1/models for the available models."
            )
            reason = ErrorReason.MODEL_WITHOUT_KEY
        else:
            message = f"Unknown model '{chosen}'. See GET /api/v1/models for the options."
            reason = ErrorReason.UNKNOWN_MODEL
        raise AppError(ErrorCode.INVALID_REQUEST, message, reason=reason, details={"model": chosen})

    def _check_can_take(self, model: LLMModelConfig, messages: Sequence[Message]) -> None:
        breaker = self._breakers.get(model.id)
        if not breaker.is_available():
            message = (
                f"The model '{model.id}' is temporarily unavailable after repeated failures. "
                "Try again later or choose another model."
            )
            raise AppError(
                ErrorCode.LLM_UNAVAILABLE,
                message,
                reason=ErrorReason.MODEL_PAUSED,
                retry_after_s=math.ceil(breaker.seconds_until_available()),
                details={"model": model.id},
            )
        window = self._window_of(model)
        if window is not None and estimate_tokens(messages) > window:
            _, template = _FAILURE_ERRORS[FailureKind.CONTEXT_EXCEEDED]
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                template.format(id=model.id),
                reason=ErrorReason.DOCUMENT_TOO_LONG_FOR_MODEL,
                details={"model": model.id},
            )

    async def _run_on_model[T: BaseModel](
        self,
        task: ExtractionTask[T],
        model: LLMModelConfig,
        messages: Sequence[Message],
        usage: _Usage,
    ) -> tuple[T, tuple[str, ...]]:
        conversation = list(messages)
        best: tuple[T, tuple[str, ...]] | None = None
        while True:
            completion = await self._complete_with_retries(model, conversation)
            usage.input_tokens += completion.input_tokens
            usage.output_tokens += completion.output_tokens
            outcome = parse_output(task, completion.text)

            if outcome.value is not None:
                issues = tuple(task.review(outcome.value))
                best = (outcome.value, issues)
                if not issues:
                    return best
                problems = issues
            else:
                problems = outcome.errors

            if usage.repairs >= self._repair_attempts:
                if best is not None:
                    return best
                detail = f"{len(problems)} errors left: {problems[0]}"
                raise ModelCallError(FailureKind.INVALID_OUTPUT, detail)
            usage.repairs += 1
            conversation += [
                Message.text("assistant", completion.text),
                Message.text("user", repair_request(problems)),
            ]

    async def _complete_with_retries(
        self, model: LLMModelConfig, conversation: Sequence[Message]
    ) -> Completion:
        retry = 0
        while True:
            try:
                return await self._backend.complete(model, conversation)
            except ModelCallError as error:
                delay = _backoff(retry, error.retry_after_s)
                can_retry = error.kind is FailureKind.TRANSIENT and retry < self._max_retries
                if not can_retry or delay > MAX_RETRY_WAIT_S:
                    raise
            retry += 1
            logger.info(
                "llm call retried",
                extra={"model": model.id, "retry": retry, "delay_s": round(delay, 1)},
            )
            await self._sleep(delay)

    def _record_failure(self, model: LLMModelConfig, error: ModelCallError) -> None:
        breaker = self._breakers.get(model.id)
        match error.kind:
            case FailureKind.QUOTA_EXHAUSTED:
                breaker.pause(max(error.retry_after_s or 0.0, QUOTA_PAUSE_S))
            case FailureKind.CONFIGURATION:
                logger.error(
                    "llm model misconfigured", extra={"model": model.id, "detail": error.detail}
                )
                breaker.pause(CONFIGURATION_PAUSE_S)
            case FailureKind.TRANSIENT:
                breaker.record_failure()
            case _:
                pass


def _messages_for(
    model: LLMModelConfig, instructions: str, content: Sequence[ContentPart]
) -> list[Message] | None:
    """The request for this model, or None when it cannot see required images."""
    if not model.vision:
        if any(isinstance(part, ImagePart) and part.required for part in content):
            return None
        content = [part for part in content if not isinstance(part, ImagePart)]
    return [Message.text("system", instructions), Message("user", tuple(content))]


def parse_output[T: BaseModel](task: ExtractionTask[T], text: str) -> ParseOutcome[T]:
    payload = extract_json_object(text)
    if payload is None:
        return ParseOutcome(None, ("The answer does not contain a JSON object.",))
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        error = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."
        return ParseOutcome(None, (error,))
    try:
        value = task.output_type.model_validate(data)
    except ValidationError as exc:
        return ParseOutcome(None, tuple(format_validation_errors(exc)))
    rule_errors = tuple(task.validate(value))
    if rule_errors:
        return ParseOutcome(None, rule_errors)
    return ParseOutcome(value, ())


def extract_json_object(text: str) -> str | None:
    """The outermost JSON object in the answer, ignoring Markdown fences and surrounding prose."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        return None
    return text[start : end + 1]


def format_validation_errors(error: ValidationError) -> list[str]:
    """Schema errors as `path: message`, without the rejected values (document content)."""
    messages = [
        f"{_location(detail['loc'])}: {detail['msg']}"
        for detail in error.errors(include_url=False, include_input=False)
    ]
    if len(messages) > MAX_REPORTED_ERRORS:
        hidden = len(messages) - MAX_REPORTED_ERRORS
        messages = [*messages[:MAX_REPORTED_ERRORS], f"... and {hidden} more errors."]
    return messages


def repair_request(errors: Sequence[str]) -> str:
    listed = "\n".join(f"- {error}" for error in errors[:MAX_REPORTED_ERRORS])
    return (
        "Your previous answer has these problems:\n"
        f"{listed}\n\n"
        "Fix them by checking the document again. Answer with the complete corrected JSON "
        "object, not only the changed parts, and do not add anything that is not in the document."
    )


def _location(loc: tuple[int | str, ...]) -> str:
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else part
    return path or "root"


def _suggested_wait(error: ModelCallError) -> int | None:
    """Seconds the client should wait before trying this model again, when it is known."""
    match error.kind:
        case FailureKind.QUOTA_EXHAUSTED:
            return math.ceil(max(error.retry_after_s or 0.0, QUOTA_PAUSE_S))
        case FailureKind.TRANSIENT if error.retry_after_s is not None:
            return math.ceil(error.retry_after_s)
        case _:
            return None


def _backoff(retry: int, retry_after_s: float | None) -> float:
    if retry_after_s is not None:
        return retry_after_s
    delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2.0**retry)
    return delay * random.uniform(0.5, 1.0)  # noqa: S311 - jitter, not security


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _log_run(  # noqa: PLR0913 - one structured log line per run
    task_name: str,
    model_id: str,
    usage: _Usage,
    started: float,
    *,
    outcome: FailureKind | None = None,
    detail: str = "",
    warnings: int = 0,
) -> None:
    logger.log(
        logging.INFO if outcome is None else logging.WARNING,
        "llm run finished",
        extra={
            "task": task_name,
            "model": model_id,
            "outcome": outcome or "success",
            "detail": detail,
            "repairs": usage.repairs,
            "warnings": warnings,
            "duration_ms": _ms(started),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    )
