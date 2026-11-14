from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.error_handlers import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.core.config import LLMCatalog, LLMModelConfig, ProviderInfo, Settings
from app.core.errors import AppError, ErrorCode, ErrorReason
from app.documents.registry import extract
from app.llm.circuit_breaker import BreakerRegistry
from app.llm.client import Completion, Message, TextPart
from app.llm.errors import FailureKind, LLMRunError, ModelCallError
from app.llm.structured import QUOTA_PAUSE_S, ExtractionTask, StructuredRunner
from tests.base.pdf_builders import text_pdf

FLASH = LLMModelConfig(id="flash", model="gemini/flash")


class Answer(BaseModel):
    title: str


TASK = ExtractionTask(name="test", output_type=Answer, instructions="Return JSON.")


def _client(error: AppError) -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.get("/fail")
    def fail() -> None:
        raise error

    return TestClient(app, raise_server_exceptions=False)


def test_reason_details_and_retry_after_reach_the_client() -> None:
    error = AppError(
        ErrorCode.LLM_UNAVAILABLE,
        reason=ErrorReason.QUOTA_EXHAUSTED,
        retry_after_s=900,
        details={"model": "flash"},
    )

    response = _client(error).get("/fail")

    body = response.json()["error"]
    assert body["reason"] == "quota_exhausted"
    assert body["details"] == {"model": "flash"}
    assert response.headers["Retry-After"] == "900"


def test_errors_without_reason_keep_the_original_body() -> None:
    response = _client(AppError(ErrorCode.NO_ITEMS)).get("/fail")

    assert set(response.json()["error"]) == {"code", "message", "request_id"}


def test_too_many_pages_reports_the_limit_and_the_page_count() -> None:
    settings = Settings(max_pages=2, render_dpi=30, render_max_px=200)

    with pytest.raises(AppError) as error:
        extract(text_pdf(pages=3), "t.pdf", settings)

    assert error.value.reason is ErrorReason.TOO_MANY_PAGES
    assert error.value.details == {"limit": 2, "actual": 3}


def test_file_over_the_size_limit_reports_both_sizes() -> None:
    settings = Settings(max_file_size_mb=1)

    with pytest.raises(AppError) as error:
        extract(b"%PDF-" + b"0" * (2 * 1024 * 1024), "t.pdf", settings)

    assert error.value.reason is ErrorReason.FILE_SIZE
    assert error.value.details == {"limit_mb": 1, "actual_mb": 3}


@dataclass
class FailingBackend:
    error: ModelCallError

    async def complete(self, _: LLMModelConfig, __: Sequence[Message]) -> Completion:
        raise self.error


def _runner(error: ModelCallError, breakers: BreakerRegistry) -> StructuredRunner:
    catalog = LLMCatalog(
        default_model="flash",
        providers={"gemini": ProviderInfo(label="G", description="")},
        models=[FLASH],
    )
    return StructuredRunner(
        catalog, FailingBackend(error), max_retries=0, repair_attempts=0, breakers=breakers
    )


async def test_exhausted_quota_says_how_long_the_model_is_paused() -> None:
    breakers = BreakerRegistry()
    runner = _runner(ModelCallError(FailureKind.QUOTA_EXHAUSTED, "quota"), breakers)

    with pytest.raises(LLMRunError) as error:
        await runner.run(TASK, [TextPart("x")])

    assert error.value.reason is ErrorReason.QUOTA_EXHAUSTED
    assert error.value.retry_after_s == QUOTA_PAUSE_S
    assert error.value.details == {"model": "flash"}


async def test_a_paused_model_reports_the_remaining_wait() -> None:
    clock = [1000.0]
    breakers = BreakerRegistry(clock=lambda: clock[0])
    runner = _runner(ModelCallError(FailureKind.QUOTA_EXHAUSTED, "quota"), breakers)
    with pytest.raises(LLMRunError):
        await runner.run(TASK, [TextPart("x")])
    clock[0] += 600

    with pytest.raises(AppError) as error:
        await runner.run(TASK, [TextPart("x")])

    assert error.value.reason is ErrorReason.MODEL_PAUSED
    assert error.value.retry_after_s == QUOTA_PAUSE_S - 600


async def test_a_model_that_does_not_respond_has_no_fixed_wait() -> None:
    runner = _runner(ModelCallError(FailureKind.TRANSIENT, "timeout"), BreakerRegistry())

    with pytest.raises(LLMRunError) as error:
        await runner.run(TASK, [TextPart("x")])

    assert error.value.reason is ErrorReason.MODEL_NOT_RESPONDING
    assert error.value.retry_after_s is None
