"""Classification of model call failures.

Each kind decides what the engine does next:

- TRANSIENT (per-minute 429, 5xx, timeout, connection): retry with backoff, then next model.
- QUOTA_EXHAUSTED (daily quota, billing): no retry; the model is paused until it resets.
- CONFIGURATION (invalid key, unknown model, rejected request): no retry; logged as an error.
- REFUSED (safety block, empty answer): next model.
- TRUNCATED (output limit reached): next model.
- CONTEXT_EXCEEDED (input too long for the model): next model.
- INVALID_OUTPUT (JSON or rules still invalid after the repair attempts): next model.
"""

import re
from enum import StrEnum

from litellm import exceptions as litellm_errors

from app.core.errors import AppError, ErrorCode

_MAX_DETAIL_CHARS = 300
_SECRET = re.compile(
    r"(?i)((?:api[_-]?)?key|token|authorization)([=:]\s*(?:bearer\s+)?)[^\s&\"',]+"
    r"|AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{16,}"
)
_PER_MINUTE_HINTS = ("perminute", "per minute", "per_minute", "rpm", "tpm")
_QUOTA_HINTS = ("perday", "per day", "per_day", "daily", "billing", "insufficient_quota", "credit")
_RETRY_DELAY = re.compile(
    r"retry(?:[ _-]?delay|[ _-]?after| in)\W*(\d+(?:\.\d+)?)\s*s", re.IGNORECASE
)


class FailureKind(StrEnum):
    TRANSIENT = "transient"
    QUOTA_EXHAUSTED = "quota_exhausted"
    CONFIGURATION = "configuration"
    REFUSED = "refused"
    TRUNCATED = "truncated"
    CONTEXT_EXCEEDED = "context_exceeded"
    INVALID_OUTPUT = "invalid_output"


class ModelCallError(Exception):
    """A failed model call. `detail` is safe to log: it never contains document content."""

    def __init__(
        self, kind: FailureKind, detail: str, *, retry_after_s: float | None = None
    ) -> None:
        self.kind = kind
        self.detail = detail[:_MAX_DETAIL_CHARS]
        self.retry_after_s = retry_after_s
        super().__init__(f"{kind}: {self.detail}")


class LLMRunError(AppError):
    """The chosen model could not produce a valid result. `kind` is why, when it was called."""

    def __init__(
        self, code: ErrorCode, message: str | None = None, *, kind: FailureKind | None = None
    ) -> None:
        super().__init__(code, message)
        self.kind = kind


def redact_secrets(text: str) -> str:
    """Removes API keys that providers sometimes echo in error messages or request URLs."""
    return _SECRET.sub("[REDACTED]", text)


def classify_exception(exc: Exception) -> ModelCallError:
    detail = redact_secrets(f"{type(exc).__name__}: {exc}")
    match exc:
        case litellm_errors.ContextWindowExceededError():
            kind = FailureKind.CONTEXT_EXCEEDED
        case litellm_errors.ContentPolicyViolationError():
            kind = FailureKind.REFUSED
        case litellm_errors.PaymentRequiredError() | litellm_errors.BudgetExceededError():
            kind = FailureKind.QUOTA_EXHAUSTED
        case litellm_errors.RateLimitError():
            return _classify_rate_limit(exc, detail)
        case (
            litellm_errors.AuthenticationError()
            | litellm_errors.PermissionDeniedError()
            | litellm_errors.NotFoundError()
            | litellm_errors.UnsupportedParamsError()
            | litellm_errors.BadRequestError()
            | litellm_errors.UnprocessableEntityError()
        ):
            kind = FailureKind.CONFIGURATION
        case _:
            # Timeouts, connection errors, 5xx and anything unexpected from a provider SDK.
            kind = FailureKind.TRANSIENT
    return ModelCallError(kind, detail)


def _classify_rate_limit(exc: Exception, detail: str) -> ModelCallError:
    message = str(exc).lower()
    retry_after_s = _retry_after(exc, message)
    is_per_minute = any(hint in message for hint in _PER_MINUTE_HINTS)
    if not is_per_minute and any(hint in message for hint in _QUOTA_HINTS):
        return ModelCallError(FailureKind.QUOTA_EXHAUSTED, detail, retry_after_s=retry_after_s)
    return ModelCallError(FailureKind.TRANSIENT, detail, retry_after_s=retry_after_s)


def _retry_after(exc: Exception, message: str) -> float | None:
    headers = getattr(exc, "headers", None)
    if isinstance(headers, dict):
        value = headers.get("retry-after") or headers.get("Retry-After")
        if isinstance(value, str) and value.replace(".", "", 1).isdigit():
            return float(value)
    match = _RETRY_DELAY.search(message)
    return float(match.group(1)) if match else None
