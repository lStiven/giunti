from typing import Any

from app.documents.models import (
    DocumentFormat,
    DocumentPage,
    DocumentWarning,
    ExtractedDocument,
    PageSource,
)
from app.extraction.grounding import (
    appears_in,
    document_warnings,
    grounding_review,
    missing_item_numbers,
    normalize,
)
from app.extraction.schema import ExtractedQuestionnaire

PAGE_ONE = """\
1. Quale e la capitale d'Italia?
A) Milano
**B) Roma**
2. Mi sento nervoso
3. Dormo bene"""


def _page(number: int, text: str, source: PageSource = PageSource.TEXT_LAYER) -> DocumentPage:
    return DocumentPage(
        number=number,
        text=text,
        image_png=None,
        char_count=len(text),
        figure_coverage=0.0,
        source=source,
    )


def _document(*pages: DocumentPage) -> ExtractedDocument:
    return ExtractedDocument(document_format=DocumentFormat.PDF, filename="t.pdf", pages=pages)


def _questionnaire(*items: dict[str, Any]) -> ExtractedQuestionnaire:
    return ExtractedQuestionnaire.model_validate({"idioma": "it", "items": list(items)})


def _choice(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    item: dict[str, Any] = {
        "numero": 1,
        "enunciado": "Quale e la capitale d'Italia?",
        "tipo": "seleccion_multiple",
        "alternativas": [{"valor": "A", "texto": "Milano"}, {"valor": "B", "texto": "Roma"}],
        "respuesta_correcta": ["B"],
        "evidencia": "**B) Roma**",
        "pagina": 1,
    }
    return {**item, **fields}


def _open(number: int, statement: str) -> dict[str, Any]:
    return {"numero": number, "enunciado": statement, "tipo": "desarrollo", "pagina": 1}


def _issues(document: ExtractedDocument, *items: dict[str, Any]) -> list[str]:
    return grounding_review(document)(_questionnaire(*items))


def test_normalize_ignores_marks_case_spacing_and_typographic_quotes() -> None:
    assert normalize("**B)  Roma**\n<u>d\u2019Italia</u> | ==X==") == "b) roma d'italia x"


def test_fragments_with_small_extraction_noise_are_found() -> None:
    text = normalize(PAGE_ONE)

    assert appears_in("Quale è la capitale d'Italia?", text)
    assert not appears_in("Qual è il fiume più lungo del mondo?", text)


def test_extraction_faithful_to_the_document_has_no_issues() -> None:
    document = _document(_page(1, PAGE_ONE))

    issues = _issues(document, _choice(), _open(2, "Mi sento nervoso"), _open(3, "Dormo bene"))

    assert issues == []


def test_invented_statement_is_reported() -> None:
    issues = _issues(
        _document(_page(1, PAGE_ONE)),
        _choice(enunciado="Qual è il fiume più lungo del mondo?"),
        _open(2, "Mi sento nervoso"),
        _open(3, "Dormo bene"),
    )

    assert issues == [
        (
            "items[0] (numero 1): the enunciado was not found on page 1; copy it literally "
            "from the document or remove the item if it is not there."
        )
    ]


def test_invented_option_texts_are_reported_with_their_values() -> None:
    options = [{"valor": "A", "texto": "Milano"}, {"valor": "B", "texto": "Firenze"}]

    issues = _issues(
        _document(_page(1, PAGE_ONE)),
        _choice(alternativas=options),
        _open(2, "Mi sento nervoso"),
        _open(3, "Dormo bene"),
    )

    assert issues == [
        (
            "items[0] (numero 1): the texto of the options B was not found on page 1; copy them "
            "literally."
        )
    ]


def test_answer_evidence_that_is_not_in_the_document_is_reported() -> None:
    issues = _issues(
        _document(_page(1, PAGE_ONE)),
        _choice(evidencia="Soluzioni: 1-A"),
        _open(2, "Mi sento nervoso"),
        _open(3, "Dormo bene"),
    )

    assert len(issues) == 1
    assert "the evidencia was not found in the document" in issues[0]


def test_answer_key_on_another_page_counts_as_evidence() -> None:
    document = _document(_page(1, PAGE_ONE), _page(2, "Soluzioni: 1-B"))

    issues = _issues(
        document,
        _choice(evidencia="Soluzioni: 1-B"),
        _open(2, "Mi sento nervoso"),
        _open(3, "Dormo bene"),
    )

    assert issues == []


def test_item_continuing_on_the_next_page_is_found() -> None:
    document = _document(_page(1, "1. Leggi il testo"), _page(2, "e rispondi alla domanda."))

    assert _issues(document, _open(1, "Leggi il testo e rispondi alla domanda.")) == []


def test_numbers_skipped_in_the_middle_are_reported() -> None:
    issues = _issues(_document(_page(1, PAGE_ONE)), _choice(), _open(3, "Dormo bene"))

    assert issues == [
        "Item numbers 2 appear in the document but were not extracted; add them if they are items."
    ]


def test_items_after_the_last_extracted_one_are_reported() -> None:
    issues = _issues(_document(_page(1, PAGE_ONE)), _choice())

    assert issues[-1].startswith("Item numbers 2, 3 appear in the document")


def test_pages_without_text_layer_are_not_checked() -> None:
    document = _document(_page(1, "", PageSource.IMAGE_ONLY))

    assert _issues(document, _choice(enunciado="Anything read from the image")) == []


def test_items_read_from_scanned_pages_produce_a_warning() -> None:
    document = _document(_page(1, PAGE_ONE), _page(2, "", PageSource.IMAGE_ONLY))
    questionnaire = _questionnaire(_choice(), _open(2, "From the scan") | {"pagina": 2})

    warnings = document_warnings(document, questionnaire)

    assert len(warnings) == 1
    assert warnings[0].startswith("Pages 2 have no text layer")


def test_sheets_with_missing_formula_values_produce_a_warning() -> None:
    page = DocumentPage(
        number=1,
        text="| a |",
        image_png=None,
        char_count=1,
        figure_coverage=0.0,
        source=PageSource.TEXT_LAYER,
        warnings=(DocumentWarning.MISSING_FORMULA_VALUES,),
    )

    warnings = document_warnings(_document(page), _questionnaire(_open(1, "a")))

    assert warnings[0].startswith("Sheets 1 have formulas without saved values")


def test_review_of_a_part_only_looks_for_numbers_on_its_pages() -> None:
    document = _document(_page(1, "1. Prima domanda"), _page(2, "2. Seconda domanda"))

    review = grounding_review(document, extracted_pages=[1])

    assert review(_questionnaire(_open(1, "Prima domanda"))) == []


def test_items_lost_between_parts_are_found_in_the_whole_document() -> None:
    document = _document(
        _page(1, "1. Prima domanda"), _page(2, "2. Seconda domanda"), _page(3, "3. Terza")
    )
    merged = _questionnaire(_open(1, "Prima domanda"), _open(3, "Terza") | {"pagina": 3})

    assert missing_item_numbers(document, merged) == [
        (
            "Item numbers 2 appear in the document but were not extracted; add them if they "
            "are items."
        )
    ]
