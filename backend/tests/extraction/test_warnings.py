from app.documents.models import DocumentFormat, DocumentPage, ExtractedDocument, PageSource
from app.extraction.grounding import review_warnings
from app.extraction.schema import ExtractedQuestionnaire
from app.extraction.warnings import ExtractionWarning, WarningCode


def _document(*texts: str) -> ExtractedDocument:
    pages = tuple(
        DocumentPage(
            number=number,
            text=text,
            image_png=None,
            char_count=len(text),
            figure_coverage=0.0,
            source=PageSource.TEXT_LAYER,
        )
        for number, text in enumerate(texts, start=1)
    )
    return ExtractedDocument(document_format=DocumentFormat.PDF, filename="t.pdf", pages=pages)


def _questionnaire(*items: dict[str, object]) -> ExtractedQuestionnaire:
    return ExtractedQuestionnaire.model_validate({"idioma": "it", "items": list(items)})


def _open(number: int, statement: str, page: int = 1) -> dict[str, object]:
    return {"numero": number, "enunciado": statement, "tipo": "desarrollo", "pagina": page}


def test_items_not_found_are_grouped_in_one_warning_with_their_final_numbers() -> None:
    document = _document("1. Descrivi la tua giornata.\n2. Racconta un viaggio.")
    questionnaire = _questionnaire(
        _open(1, "Descrivi la tua giornata."),
        _open(2, "Una domanda che non esiste da nessuna parte."),
        _open(3, "Un'altra domanda inventata dal modello."),
    )

    warnings = review_warnings(document, questionnaire)

    statement = next(w for w in warnings if w.code is WarningCode.STATEMENT_NOT_FOUND)
    assert statement.items == (2, 3)


def test_document_numbers_missing_from_the_result_are_reported() -> None:
    document = _document("1. Prima domanda?\n2. Seconda domanda?\n3. Terza domanda?")
    questionnaire = _questionnaire(_open(1, "Prima domanda?"), _open(2, "Seconda domanda?"))

    warnings = review_warnings(document, questionnaire)

    assert [w.code for w in warnings] == [WarningCode.MISSING_ITEM_NUMBERS]
    assert warnings[0].items == (3,)


def test_a_clean_result_has_no_warnings() -> None:
    document = _document("1. Prima domanda?")

    assert review_warnings(document, _questionnaire(_open(1, "Prima domanda?"))) == []


def test_warnings_are_sent_as_objects_with_code_items_and_pages() -> None:
    warning = ExtractionWarning(WarningCode.SCANNED_PAGES, "msg", items=(4,), pages=(2,))

    assert warning.as_json() == {
        "code": "scanned_pages",
        "message": "msg",
        "items": [4],
        "pages": [2],
    }
