"""`POST /api/v1/questionnaires`: one multipart file (and optionally the model), returns the
questionnaire JSON.

The JSON body is the contract fixed by the problem statement; data about the run goes in
headers: the model and reasoning mode used, token usage, LLM time, repairs and warnings (a JSON
list of objects with `code`, `message`, `items` and `pages`; see `app.extraction.warnings`).
"""

import json
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.api.error_handlers import ErrorResponse
from app.auth.dependencies import AuthenticatedClient, require_extraction_quota
from app.core.config import ReasoningMode, get_settings
from app.documents.security import BYTES_PER_MB
from app.extraction.schema import Questionnaire
from app.extraction.service import ExtractionOutcome, QuestionnaireExtractor
from app.llm.structured import StructuredRunner

MAX_WARNING_HEADER_ITEMS = 20

router = APIRouter(prefix="/api/v1", tags=["questionnaires"])


@lru_cache
def get_extractor() -> QuestionnaireExtractor:
    """One extractor per process, so circuit breakers are shared across requests."""
    settings = get_settings()
    return QuestionnaireExtractor(StructuredRunner.from_settings(settings), settings)


@router.post(
    "/questionnaires",
    response_model=Questionnaire,
    responses={
        status: {"model": ErrorResponse} for status in (401, 403, 413, 415, 422, 429, 500, 502, 503)
    },
)
async def extract_questionnaire(  # noqa: PLR0913 - FastAPI request parts and dependencies
    response: Response,
    *,
    client: Annotated[AuthenticatedClient, Depends(require_extraction_quota)],
    extractor: Annotated[QuestionnaireExtractor, Depends(get_extractor)],
    file: Annotated[UploadFile, File(description="PDF, DOCX or XLSX questionnaire")],
    model: Annotated[
        str | None,
        Form(description="Model id from GET /api/v1/models; the default model when omitted"),
    ] = None,
    mode: Annotated[
        ReasoningMode | None,
        Form(
            description="fast: less reasoning, faster and cheaper. precise: more reasoning, for "
            "hard documents. The catalog default when omitted; precise for models without fast"
        ),
    ] = None,
) -> Questionnaire:
    # Read one byte over the limit so oversized files are rejected without loading them whole.
    limit = get_settings().max_file_size_mb * BYTES_PER_MB
    data = await file.read(limit + 1)
    outcome = await extractor.process(
        data,
        file.filename or "",
        model_id=model or None,
        mode=mode,
        allowed_modes=client.allowed_modes,
    )
    _set_run_headers(response, outcome)
    return outcome.questionnaire


def _set_run_headers(response: Response, outcome: ExtractionOutcome) -> None:
    response.headers["X-LLM-Model"] = outcome.model_id
    response.headers["X-LLM-Mode"] = outcome.mode
    response.headers["X-LLM-Input-Tokens"] = str(outcome.input_tokens)
    response.headers["X-LLM-Output-Tokens"] = str(outcome.output_tokens)
    response.headers["X-LLM-Repairs"] = str(outcome.repairs)
    response.headers["X-LLM-Duration-Ms"] = str(outcome.llm_duration_ms)
    response.headers["X-Extraction-Parts"] = str(outcome.parts)
    warnings = [warning.as_json() for warning in outcome.warnings[:MAX_WARNING_HEADER_ITEMS]]
    response.headers["X-Extraction-Warnings"] = json.dumps(warnings, ensure_ascii=True)
