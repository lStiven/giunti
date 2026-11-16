import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pytest

from app.core.config import LLMCatalog, LLMModelConfig, ProviderInfo, Settings
from app.documents.models import DocumentFormat, DocumentPage, ExtractedDocument, PageSource
from app.extraction.answer_key import (
    INSTRUCTIONS as KEY_INSTRUCTIONS,
)
from app.extraction.answer_key import (
    answer_key_pages,
    fill_from_answer_key,
)
from app.extraction.schema import ExtractedQuestionnaire
from app.extraction.service import QuestionnaireExtractor
from app.extraction.warnings import WarningCode
from app.llm.client import Completion, ImagePart, Message, TextPart
from app.llm.errors import FailureKind, ModelCallError
from app.llm.structured import StructuredRunner
from tests.base.pdf_builders import lines_pdf

FLASH = LLMModelConfig(id="flash", model="gemini/flash")
OPTIONS = [{"valor": "A", "texto": "Roma"}, {"valor": "B", "texto": "Milano"}]

type Reply = Callable[[Sequence[Message]], Completion]


@dataclass
class ScriptedBackend:
    """Answers each call with `reply`; records the calls made with the answer-key instructions."""

    reply: Reply
    key_calls: list[Sequence[Message]] = field(default_factory=list)
    calls: int = 0

    async def complete(self, _: LLMModelConfig, messages: Sequence[Message]) -> Completion:
        self.calls += 1
        if _is_key_call(messages):
            self.key_calls.append(messages)
        return self.reply(messages)


def _is_key_call(messages: Sequence[Message]) -> bool:
    first = messages[0].parts[0]
    return isinstance(first, TextPart) and first.text == KEY_INSTRUCTIONS


def _runner(backend: ScriptedBackend) -> StructuredRunner:
    catalog = LLMCatalog(
        default_model="flash",
        providers={"gemini": ProviderInfo(label="G", description="")},
        models=[FLASH],
    )
    return StructuredRunner(catalog, backend, max_retries=0, repair_attempts=0)


def _document(*texts: str) -> ExtractedDocument:
    pages = tuple(
        DocumentPage(
            number=number,
            text=text,
            image_png=f"png{number}".encode(),
            char_count=len(text),
            figure_coverage=0.0,
            source=PageSource.TEXT_LAYER,
        )
        for number, text in enumerate(texts, start=1)
    )
    return ExtractedDocument(document_format=DocumentFormat.PDF, filename="t.pdf", pages=pages)


def _mc(number: int, answer: list[str] | None = None, page: int = 1) -> dict[str, object]:
    return {
        "numero": number,
        "enunciado": f"Domanda {number}",
        "tipo": "seleccion_multiple",
        "alternativas": OPTIONS,
        "respuesta_correcta": answer,
        "evidencia": f"**{answer[0]}**" if answer else None,
        "pagina": page,
    }


def _questionnaire(*items: dict[str, object]) -> ExtractedQuestionnaire:
    return ExtractedQuestionnaire.model_validate({"idioma": "it", "items": list(items)})


def _key_reply(*answers: dict[str, object]) -> Reply:
    def reply(_: Sequence[Message]) -> Completion:
        return Completion(json.dumps({"respuestas": list(answers)}), 7, 3)

    return reply


def _never(_: Sequence[Message]) -> Completion:
    message = "no model call was expected"
    raise AssertionError(message)


KEY_DOCUMENT = _document("1. Domanda 1", "2. Domanda 2", "Tabla de respuestas correctas")


def test_key_pages_include_singular_headers_written_with_formatting_marks() -> None:
    document = _document(
        "1. Domanda",
        "Tabla de respuestas correctas\n| 1 | C |",
        "| **Posición** | **Respuesta** **correcta** |\n| 14 | B |",
        "Fin del cuadernillo",
    )

    assert answer_key_pages(document) == (2, 3)


@pytest.mark.parametrize(
    "sentence",
    [
        "(3 pts. por la respuesta correcta = 3 pts.)",
        "5. Por cada respuesta correcta obtendrá el puntaje indicado a la derecha.",
        "1 punto per risposta corretta",
        "En las preguntas 1 - 5, marque la letra correcta A - G en su hoja de respuestas.",
        "Choose the correct answer for each question. Mark only one option.",
    ],
)
def test_key_phrases_inside_sentences_are_not_key_pages(sentence: str) -> None:
    document = _document(f"1. Domanda\n{sentence}", "Fine")

    assert answer_key_pages(document) == ()


@pytest.mark.parametrize(
    "heading",
    [
        "**Soluzioni**: 1-B, 2-C, 3-A, 4-D, 5-B, 6-C, 7-A, 8-B, 9-D, 10-A",
        "Tabla de respuestas correctas - Examen 1",
        "| **Respuesta correcta:** <u>C</u> | **Eje de Habilidad:** Geometría |",
        "## Sheet: Answer key (hidden)",
    ],
)
def test_key_headings_are_key_pages(heading: str) -> None:
    document = _document("1. Domanda", heading)

    assert answer_key_pages(document) == (2,)


def test_a_numbered_table_right_after_a_key_page_continues_the_key() -> None:
    rows = "| 14 | B |\n| 15 | A |\n| 16 | D |"
    document = _document(rows, "Soluzioni", rows, rows, "Fine")

    assert answer_key_pages(document) == (2, 3, 4)


async def test_no_extra_call_when_every_answerable_item_has_an_answer() -> None:
    backend = ScriptedBackend(_never)
    questionnaire = _questionnaire(_mc(1, ["A"]), _mc(2, ["B"]))

    fill = await fill_from_answer_key(
        _runner(backend), KEY_DOCUMENT, questionnaire, "flash", "precise"
    )

    assert backend.calls == 0
    assert fill.questionnaire == questionnaire
    assert fill.warnings == ()


async def test_no_extra_call_without_answer_key_pages() -> None:
    backend = ScriptedBackend(_never)
    questionnaire = _questionnaire(_mc(1))

    fill = await fill_from_answer_key(
        _runner(backend), _document("1. Domanda 1"), questionnaire, "flash", "precise"
    )

    assert backend.calls == 0
    assert fill.questionnaire == questionnaire


async def test_fills_only_the_items_without_answer_and_keeps_the_found_ones() -> None:
    backend = ScriptedBackend(
        _key_reply({"numero": 2, "respuesta_correcta": ["b"], "evidencia": "2 B"})
    )
    questionnaire = _questionnaire(_mc(1, ["A"]), _mc(2, page=2))

    fill = await fill_from_answer_key(
        _runner(backend), KEY_DOCUMENT, questionnaire, "flash", "precise"
    )

    first, second = fill.questionnaire.items
    assert first == questionnaire.items[0]
    assert second.correct_answer == ["B"]
    assert second.evidence == "2 B"
    assert fill.warnings == ()
    assert fill.result is not None
    assert fill.result.input_tokens == 7


async def test_the_key_call_carries_the_key_pages_with_images_and_the_pending_items() -> None:
    backend = ScriptedBackend(_key_reply())
    questionnaire = _questionnaire(_mc(1, ["A"]), _mc(2, page=2))

    await fill_from_answer_key(_runner(backend), KEY_DOCUMENT, questionnaire, "flash", "precise")

    parts = backend.key_calls[0][-1].parts
    texts = " ".join(part.text for part in parts if isinstance(part, TextPart))
    assert "=== Answer key page 3 ===" in texts
    assert "=== Item page 2 (text only) ===" in texts
    assert '"numero": 2' in texts
    assert '"numero": 1' not in texts
    assert [part.png for part in parts if isinstance(part, ImagePart)] == [b"png3"]


async def test_matching_pairs_are_written_with_the_item_values() -> None:
    matching = {
        "numero": 1,
        "enunciado": "Abbina",
        "tipo": "emparejamiento",
        "premisas": [{"valor": 1, "texto": "Roma"}, {"valor": 2, "texto": "Parigi"}],
        "alternativas": [{"valor": "a", "texto": "Italia"}, {"valor": "b", "texto": "Francia"}],
        "pagina": 1,
    }
    backend = ScriptedBackend(
        _key_reply({"numero": 1, "respuesta_correcta": ["1-A", "2-B"], "evidencia": "1-a 2-b"})
    )

    fill = await fill_from_answer_key(
        _runner(backend), KEY_DOCUMENT, _questionnaire(matching), "flash", "precise"
    )

    assert fill.questionnaire.items[0].correct_answer == ["1-a", "2-b"]


async def test_items_the_key_does_not_answer_are_reported() -> None:
    backend = ScriptedBackend(
        _key_reply({"numero": 1, "respuesta_correcta": ["A"], "evidencia": "1 A"})
    )

    fill = await fill_from_answer_key(
        _runner(backend), KEY_DOCUMENT, _questionnaire(_mc(1), _mc(2)), "flash", "precise"
    )

    assert fill.questionnaire.items[0].correct_answer == ["A"]
    assert fill.questionnaire.items[1].correct_answer is None
    (warning,) = fill.warnings
    assert warning.code is WarningCode.ANSWERS_NOT_IN_KEY
    assert warning.items == (2,)
    assert warning.pages == (3,)


async def test_an_answer_for_an_item_not_listed_keeps_the_questionnaire_unchanged() -> None:
    backend = ScriptedBackend(
        _key_reply({"numero": 9, "respuesta_correcta": ["A"], "evidencia": "9 A"})
    )
    questionnaire = _questionnaire(_mc(1))

    fill = await fill_from_answer_key(
        _runner(backend), KEY_DOCUMENT, questionnaire, "flash", "precise"
    )

    assert fill.questionnaire == questionnaire
    assert fill.warnings[0].code is WarningCode.ANSWER_KEY_UNREAD


async def test_an_answer_that_is_not_an_alternative_keeps_the_questionnaire_unchanged() -> None:
    backend = ScriptedBackend(
        _key_reply({"numero": 1, "respuesta_correcta": ["Z"], "evidencia": "1 Z"})
    )
    questionnaire = _questionnaire(_mc(1))

    fill = await fill_from_answer_key(
        _runner(backend), KEY_DOCUMENT, questionnaire, "flash", "precise"
    )

    assert fill.questionnaire == questionnaire
    assert len(fill.warnings) == 1


async def test_a_failing_model_keeps_the_questionnaire_with_a_warning() -> None:
    def refuse(_: Sequence[Message]) -> Completion:
        raise ModelCallError(FailureKind.REFUSED, "blocked")

    questionnaire = _questionnaire(_mc(1))

    fill = await fill_from_answer_key(
        _runner(ScriptedBackend(refuse)), KEY_DOCUMENT, questionnaire, "flash", "precise"
    )

    assert fill.questionnaire == questionnaire
    assert fill.result is None
    (warning,) = fill.warnings
    assert warning.code is WarningCode.ANSWER_KEY_UNREAD
    assert warning.items == (1,)


def _service_reply(messages: Sequence[Message]) -> Completion:
    if _is_key_call(messages):
        answers = [{"numero": 1, "respuesta_correcta": ["B"], "evidencia": "1 B"}]
        return Completion(json.dumps({"respuestas": answers}), 11, 2)
    item = {
        "numero": 1,
        "enunciado": "Qual e la capitale?",
        "tipo": "seleccion_multiple",
        "alternativas": [{"valor": "A", "texto": "Milano"}, {"valor": "B", "texto": "Roma"}],
        "pagina": 1,
    }
    return Completion(json.dumps({"idioma": "it", "items": [item]}), 10, 5)


def _service(backend: ScriptedBackend, *, key_pass: bool) -> QuestionnaireExtractor:
    settings = Settings(render_dpi=30, render_max_px=200, extraction_answer_key_pass=key_pass)
    return QuestionnaireExtractor(_runner(backend), settings)


PDF_WITH_KEY = lines_pdf(
    ["1. Qual e la capitale?", "A) Milano", "B) Roma"], ["Soluzioni", "| 1 | B |"]
)


async def test_service_fills_answers_from_the_key_and_counts_the_extra_call() -> None:
    backend = ScriptedBackend(_service_reply)

    outcome = await _service(backend, key_pass=True).process(PDF_WITH_KEY, "t.pdf")

    assert outcome.questionnaire.items[0].correct_answer == ["B"]
    assert backend.calls == 2
    assert outcome.parts == 1
    assert outcome.input_tokens == 21
    assert outcome.output_tokens == 7
    assert outcome.warnings == ()


async def test_service_skips_the_key_pass_when_it_is_turned_off() -> None:
    backend = ScriptedBackend(_service_reply)

    outcome = await _service(backend, key_pass=False).process(PDF_WITH_KEY, "t.pdf")

    assert outcome.questionnaire.items[0].correct_answer is None
    assert backend.calls == 1
    assert backend.key_calls == []
