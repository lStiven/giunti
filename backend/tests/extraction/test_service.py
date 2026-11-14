import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from app.core.config import LLMCatalog, LLMModelConfig, ProviderInfo, Settings
from app.core.errors import ErrorCode
from app.extraction.service import QuestionnaireExtractor
from app.llm.client import Completion, Message, TextPart
from app.llm.errors import FailureKind, LLMRunError, ModelCallError
from app.llm.structured import StructuredRunner
from tests.base.pdf_builders import text_pdf

FLASH = LLMModelConfig(id="flash", model="gemini/flash")
_PAGE = re.compile(r"=== Page (\d+) ===(?! \(context)")


def _item(number: int, page: int) -> dict[str, object]:
    return {
        "numero": number,
        "enunciado": f"Pagina {page}: indica quanto sei d'accordo.",
        "tipo": "desarrollo",
        "pagina": page,
    }


def _answer(*pages: int) -> Completion:
    items = [_item(page, page) for page in pages]
    return Completion(json.dumps({"idioma": "it", "items": items}), 10, 5)


@dataclass
class PagesBackend:
    """Answers with one item per extracted page; `truncate_over` pages cut the output off."""

    truncate_over: int = 99
    fail_on_page: int | None = None
    delay_s: float = 0.0
    calls: list[tuple[int, ...]] = field(default_factory=list)
    finished: list[tuple[int, ...]] = field(default_factory=list)
    models: list[str] = field(default_factory=list)

    async def complete(self, model: LLMModelConfig, messages: Sequence[Message]) -> Completion:
        text = " ".join(p.text for p in messages[-1].parts if isinstance(p, TextPart))
        pages = tuple(int(n) for n in _PAGE.findall(text))
        self.calls.append(pages)
        self.models.append(model.id)
        if self.fail_on_page in pages:
            raise ModelCallError(FailureKind.REFUSED, "blocked")
        if len(pages) > self.truncate_over:
            raise ModelCallError(FailureKind.TRUNCATED, "too long")
        await asyncio.sleep(self.delay_s * pages[0])
        self.finished.append(pages)
        return _answer(*pages)


def _extractor(backend: PagesBackend, pages_per_part: int) -> QuestionnaireExtractor:
    catalog = LLMCatalog(
        default_model="flash",
        providers={"gemini": ProviderInfo(label="G", description="")},
        models=[FLASH],
    )
    runner = StructuredRunner(catalog, backend, max_retries=0, repair_attempts=0)
    settings = Settings(
        render_dpi=30,
        render_max_px=200,
        extraction_pages_per_part=pages_per_part,
        extraction_parallel_parts=2,
    )
    return QuestionnaireExtractor(runner, settings)


async def test_long_document_is_extracted_in_parts_and_merged_in_order() -> None:
    backend = PagesBackend(delay_s=0.01)

    outcome = await _extractor(backend, pages_per_part=2).process(text_pdf(pages=5), "t.pdf")

    assert sorted(backend.calls) == [(1, 2), (3, 4), (5,)]
    assert [item.number for item in outcome.questionnaire.items] == [1, 2, 3, 4, 5]
    assert outcome.parts == 3
    assert outcome.input_tokens == 30
    assert outcome.warnings == ()


async def test_short_document_is_a_single_call() -> None:
    backend = PagesBackend()

    outcome = await _extractor(backend, pages_per_part=8).process(text_pdf(pages=3), "t.pdf")

    assert backend.calls == [(1, 2, 3)]
    assert outcome.parts == 1


async def test_part_cut_off_by_the_output_limit_is_split_and_retried() -> None:
    backend = PagesBackend(truncate_over=2)

    outcome = await _extractor(backend, pages_per_part=4).process(text_pdf(pages=4), "t.pdf")

    assert backend.calls[0] == (1, 2, 3, 4)
    assert sorted(backend.finished) == [(1, 2), (3, 4)]
    assert [item.number for item in outcome.questionnaire.items] == [1, 2, 3, 4]
    assert outcome.parts == 2


async def test_single_page_still_cut_off_fails_the_request() -> None:
    backend = PagesBackend(truncate_over=0)

    with pytest.raises(LLMRunError) as error:
        await _extractor(backend, pages_per_part=2).process(text_pdf(pages=2), "t.pdf")

    assert error.value.code is ErrorCode.INVALID_LLM_RESPONSE
    assert error.value.kind is FailureKind.TRUNCATED


async def test_a_failing_part_fails_the_request_and_cancels_the_others() -> None:
    backend = PagesBackend(fail_on_page=1, delay_s=0.05)

    with pytest.raises(LLMRunError) as error:
        await _extractor(backend, pages_per_part=1).process(text_pdf(pages=3), "t.pdf")

    assert error.value.kind is FailureKind.REFUSED
    assert (3,) not in backend.finished
