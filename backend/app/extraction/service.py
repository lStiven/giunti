"""Use case `process(file) -> ExtractionOutcome`, independent of the HTTP transport.

Validate the chosen model, read the document, run the extraction task on that model, check the
result and strip the internal fields. Fails with NO_ITEMS when nothing is found.
"""

import asyncio
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.documents.registry import extract
from app.extraction.grounding import document_warnings
from app.extraction.prompt import build_content
from app.extraction.schema import Questionnaire
from app.extraction.task import questionnaire_task
from app.llm.structured import StructuredRunner


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    questionnaire: Questionnaire
    model_id: str
    warnings: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    repairs: int
    llm_duration_ms: int


class QuestionnaireExtractor:
    def __init__(self, runner: StructuredRunner, settings: Settings) -> None:
        self._runner = runner
        self._settings = settings

    async def process(
        self, data: bytes, filename: str, *, model_id: str | None = None
    ) -> ExtractionOutcome:
        # Fail on an unusable model before spending time reading the document.
        model = self._runner.resolve_model(model_id)
        # Reading is CPU-bound and blocking (pdfplumber, LibreOffice).
        document = await asyncio.to_thread(extract, data, filename, self._settings)
        result = await self._runner.run(
            questionnaire_task(document), build_content(document), model_id=model.id
        )
        extracted = result.value
        if not extracted.items:
            raise AppError(ErrorCode.NO_ITEMS)
        warnings = (*document_warnings(document, extracted), *result.warnings)
        return ExtractionOutcome(
            questionnaire=extracted.to_public(),
            model_id=result.model_id,
            warnings=warnings,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            repairs=result.repairs,
            llm_duration_ms=result.duration_ms,
        )
