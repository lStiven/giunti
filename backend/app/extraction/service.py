"""Use case `process(file) -> ExtractionOutcome`, independent of the HTTP transport.

Validate the chosen model, read the document, extract it in parts on that model (several at a
time), merge and check the result, and strip the internal fields. A part whose answer is cut
off by the model's output limit is split in two and retried; any other failure fails the whole
request, because an incomplete questionnaire must not look complete. Fails with NO_ITEMS when
nothing is found.
"""

import asyncio
import time
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.documents.models import ExtractedDocument
from app.documents.registry import extract
from app.extraction.chunking import Chunk, merge, plan_chunks, split_chunk
from app.extraction.grounding import document_warnings, missing_item_numbers
from app.extraction.prompt import build_content
from app.extraction.schema import ExtractedQuestionnaire, Questionnaire
from app.extraction.task import questionnaire_task
from app.llm.errors import FailureKind, LLMRunError
from app.llm.structured import StructuredResult, StructuredRunner

type PartResult = StructuredResult[ExtractedQuestionnaire]


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    questionnaire: Questionnaire
    model_id: str
    warnings: tuple[str, ...]
    parts: int
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

        started = time.perf_counter()
        run = _PartsRun(self._runner, document, model.id, self._settings.extraction_parallel_parts)
        chunks = plan_chunks(document, self._settings.extraction_pages_per_part)
        results = [
            result
            for part in await _all_or_none([run.extract(chunk) for chunk in chunks])
            for result in part
        ]
        llm_duration_ms = round((time.perf_counter() - started) * 1000)

        extracted = merge([result.value for result in results])
        if not extracted.items:
            raise AppError(ErrorCode.NO_ITEMS)
        warnings = [*document_warnings(document, extracted)]
        warnings += [warning for result in results for warning in result.warnings]
        if len(results) > 1:
            # Each part checked its own pages; this catches items lost between parts.
            warnings += missing_item_numbers(document, extracted)
        return ExtractionOutcome(
            questionnaire=extracted.to_public(),
            model_id=model.id,
            warnings=tuple(warnings),
            parts=len(results),
            input_tokens=sum(result.input_tokens for result in results),
            output_tokens=sum(result.output_tokens for result in results),
            repairs=sum(result.repairs for result in results),
            llm_duration_ms=llm_duration_ms,
        )


class _PartsRun:
    """Extraction of one document's parts on one model, with a cap on parallel calls."""

    def __init__(
        self, runner: StructuredRunner, document: ExtractedDocument, model_id: str, parallel: int
    ) -> None:
        self._runner = runner
        self._document = document
        self._model_id = model_id
        self._slots = asyncio.Semaphore(parallel)

    async def extract(self, chunk: Chunk) -> list[PartResult]:
        """The results of the chunk, split in halves while the model's output is cut off."""
        try:
            # Only the model call holds a slot: halves must not wait for their parent's slot.
            async with self._slots:
                result = await self._runner.run(
                    questionnaire_task(self._document, chunk),
                    build_content(self._document, chunk),
                    model_id=self._model_id,
                )
        except LLMRunError as error:
            if error.kind is not FailureKind.TRUNCATED or len(chunk.pages) == 1:
                raise
            first, second = split_chunk(self._document, chunk)
            halves = await _all_or_none([self.extract(first), self.extract(second)])
            return [result for half in halves for result in half]
        return [result]


async def _all_or_none[T](calls: Sequence[Awaitable[T]]) -> list[T]:
    """Runs the calls concurrently; on the first failure cancels the rest and raises it."""
    tasks = [asyncio.ensure_future(call) for call in calls]
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
