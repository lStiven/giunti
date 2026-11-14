import pytest
from litellm import exceptions as litellm_errors

from app.llm.errors import FailureKind, classify_exception, redact_secrets

MODEL = "gemini/test-model"
PROVIDER = "gemini"


@pytest.mark.parametrize(
    ("exception", "kind"),
    [
        (
            litellm_errors.ContextWindowExceededError("too long", MODEL, PROVIDER),
            FailureKind.CONTEXT_EXCEEDED,
        ),
        (
            litellm_errors.ContentPolicyViolationError("blocked", MODEL, PROVIDER),
            FailureKind.REFUSED,
        ),
        (
            litellm_errors.PaymentRequiredError("pay", MODEL, PROVIDER),
            FailureKind.QUOTA_EXHAUSTED,
        ),
        (
            litellm_errors.AuthenticationError("bad key", PROVIDER, MODEL),
            FailureKind.CONFIGURATION,
        ),
        (litellm_errors.NotFoundError("no model", MODEL, PROVIDER), FailureKind.CONFIGURATION),
        (litellm_errors.BadRequestError("bad", MODEL, PROVIDER), FailureKind.CONFIGURATION),
        (litellm_errors.Timeout("slow", MODEL, PROVIDER), FailureKind.TRANSIENT),
        (litellm_errors.APIConnectionError("down", PROVIDER, MODEL), FailureKind.TRANSIENT),
        (
            litellm_errors.ServiceUnavailableError("busy", PROVIDER, MODEL),
            FailureKind.TRANSIENT,
        ),
        (litellm_errors.InternalServerError("oops", PROVIDER, MODEL), FailureKind.TRANSIENT),
        (RuntimeError("unexpected"), FailureKind.TRANSIENT),
    ],
)
def test_provider_errors_are_classified(exception: Exception, kind: FailureKind) -> None:
    assert classify_exception(exception).kind is kind


def test_per_minute_rate_limit_is_transient_with_the_requested_delay() -> None:
    error = litellm_errors.RateLimitError(
        "You exceeded your current quota. Quota metric: requests PerMinute. retryDelay: 34s",
        PROVIDER,
        MODEL,
    )

    result = classify_exception(error)

    assert result.kind is FailureKind.TRANSIENT
    assert result.retry_after_s == 34


def test_daily_quota_is_exhausted_quota() -> None:
    error = litellm_errors.RateLimitError(
        "Quota exceeded for metric generate_content_requests PerDay", PROVIDER, MODEL
    )

    assert classify_exception(error).kind is FailureKind.QUOTA_EXHAUSTED


def test_rate_limit_retry_after_header_is_used() -> None:
    error = litellm_errors.RateLimitError(
        "slow down", PROVIDER, MODEL, headers={"retry-after": "7"}
    )

    assert classify_exception(error).retry_after_s == 7


def test_error_detail_is_truncated_and_never_contains_api_keys() -> None:
    secret = "AIzaSyD" + "x" * 32
    error = litellm_errors.AuthenticationError(
        f"denied for https://host/v1?key={secret} " + "padding " * 100, PROVIDER, MODEL
    )

    detail = classify_exception(error).detail

    assert secret not in detail
    assert len(detail) <= 300


@pytest.mark.parametrize(
    "text",
    [
        "url?key=abc123secret&alt=json",
        "Authorization: Bearer abc123secret",
        "api_key=abc123secret",
        "token: abc123secret",
        "sk-abcdefghijklmnopqrstuvwxyz",
    ],
)
def test_secrets_are_redacted(text: str) -> None:
    assert "abc123secret" not in redact_secrets(text)
    assert "abcdefghijklmnop" not in redact_secrets(text)


def test_ordinary_messages_are_not_redacted() -> None:
    message = "API key not valid. Please pass a valid API key. max_tokens: 100"

    assert redact_secrets(message) == message
