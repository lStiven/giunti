"""Use case `process(file) -> ExtractionOutcome`, independent of the HTTP transport.

Validate the chosen model, read the document, extract it in parts on that model (several at a
time), merge and check the result, read the answer key for items still without an answer (see
`answer_key`), and strip the internal fields. A part whose answer is cut
off by the model's output limit is split in two and retried; any other failure fails the whole
request, because an incomplete questionnaire must not look complete. Fails with NO_ITEMS when
nothing is found.
"""

import asyncio
import time
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass

from app.core.config import ReasoningMode, Settings
from app.core.errors import AppError, ErrorCode
from app.documents.models import ExtractedDocument
from app.documents.registry import extract
from app.extraction.answer_key import KeyAnswers, KeyFill, fill_from_answer_key
from app.extraction.chunking import Chunk, merge, plan_chunks, split_chunk
from app.extraction.grounding import document_warnings, review_warnings
from app.extraction.prompt import build_content
from app.extraction.schema import ExtractedQuestionnaire, Questionnaire
from app.extraction.task import questionnaire_task
from app.extraction.warnings import ExtractionWarning
from app.llm.errors import FailureKind, LLMRunError
from app.llm.structured import StructuredResult, StructuredRunner

type PartResult = StructuredResult[ExtractedQuestionnaire]


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    questionnaire: Questionnaire
    model_id: str
    mode: ReasoningMode
    warnings: tuple[ExtractionWarning, ...]
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
        self,
        data: bytes,
        filename: str,
        *,
        model_id: str | None = None,
        mode: ReasoningMode | None = None,
    ) -> ExtractionOutcome:
        # Fail on an unusable model before spending time reading the document.
        model = self._runner.resolve_model(model_id)
        effective_mode = self._runner.resolve_mode(model, mode)
        # Reading is CPU-bound and blocking (pdfplumber, LibreOffice).
        document = await asyncio.to_thread(extract, data, filename, self._settings)

        started = time.perf_counter()
        run = _PartsRun(
            self._runner,
            document,
            model.id,
            effective_mode,
            self._settings.extraction_parallel_parts,
        )
        chunks = plan_chunks(document, self._settings.extraction_pages_per_part)
        results = [
            result
            for part in await _all_or_none([run.extract(chunk) for chunk in chunks])
            for result in part
        ]

        extracted = merge([result.value for result in results])
        if not extracted.items:
            raise AppError(ErrorCode.NO_ITEMS)
        key_fill = KeyFill(extracted)
        if self._settings.extraction_answer_key_pass:
            key_fill = await fill_from_answer_key(
                self._runner, document, extracted, model.id, effective_mode
            )
            extracted = key_fill.questionnaire
        llm_duration_ms = round((time.perf_counter() - started) * 1000)

        # Checked again on the merged result so warnings use the final item numbers.
        warnings = [*document_warnings(document, extracted)]
        warnings += review_warnings(document, extracted)
        warnings += key_fill.warnings
        usage: list[StructuredResult[ExtractedQuestionnaire] | StructuredResult[KeyAnswers]] = [
            *results
        ]
        if key_fill.result is not None:
            usage.append(key_fill.result)
        return ExtractionOutcome(
            questionnaire=extracted.to_public(),
            model_id=model.id,
            mode=effective_mode,
            warnings=tuple(warnings),
            parts=len(results),
            input_tokens=sum(result.input_tokens for result in usage),
            output_tokens=sum(result.output_tokens for result in usage),
            repairs=sum(result.repairs for result in usage),
            llm_duration_ms=llm_duration_ms,
        )


class _PartsRun:
    """Extraction of one document's parts on one model, with a cap on parallel calls."""

    def __init__(
        self,
        runner: StructuredRunner,
        document: ExtractedDocument,
        model_id: str,
        mode: ReasoningMode,
        parallel: int,
    ) -> None:
        self._runner = runner
        self._document = document
        self._model_id = model_id
        self._mode = mode
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
                    mode=self._mode,
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
