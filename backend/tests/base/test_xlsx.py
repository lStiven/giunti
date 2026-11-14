import pytest

from app.core.errors import AppError, ErrorCode
from app.documents.models import DocumentFormat, DocumentPage, DocumentWarning, PageSource
from app.documents.xlsx import extract_xlsx
from tests.base.office_builders import (
    questionnaire_xlsx,
    xlsx_with_sheets,
    xlsx_with_uncached_formula,
)


@pytest.fixture(scope="module")
def pages() -> tuple[DocumentPage, ...]:
    document = extract_xlsx(questionnaire_xlsx(), "test.xlsx", max_pages=10)
    assert document.document_format is DocumentFormat.XLSX
    return document.pages


def test_each_non_empty_sheet_becomes_a_numbered_page(pages: tuple[DocumentPage, ...]) -> None:
    assert [page.number for page in pages] == [1, 2]
    assert pages[0].text.startswith("## Sheet: Test\n")


def test_sheet_becomes_markdown_table_without_empty_rows(pages: tuple[DocumentPage, ...]) -> None:
    lines = pages[0].text.splitlines()

    assert lines[2] == "| --- | --- | --- | --- |"
    assert lines[3] == "| N | Domanda | Mai | Sempre |"


def test_merged_cell_value_is_repeated_in_every_column(pages: tuple[DocumentPage, ...]) -> None:
    assert pages[0].text.splitlines()[1] == (
        "| Questionario | Questionario | Questionario | Questionario |"
    )


def test_cell_formatting_and_special_characters_are_kept(pages: tuple[DocumentPage, ...]) -> None:
    lines = pages[0].text.splitlines()

    assert lines[4] == "| 1 | Mi sento \\| nervoso | 0 | **1** |"
    assert lines[5] == "| 2 | Dormo bene<br>e a lungo | ==0== | <u>1</u> |"


def test_hidden_sheet_is_included_and_flagged(pages: tuple[DocumentPage, ...]) -> None:
    assert pages[1].text == "## Sheet: Chiave (hidden)\n| 1-B |\n| --- |"


def test_sheets_are_read_from_text_without_image(pages: tuple[DocumentPage, ...]) -> None:
    assert all(page.source is PageSource.TEXT_LAYER for page in pages)
    assert all(page.image_png is None for page in pages)


def test_formula_without_cached_value_produces_a_warning() -> None:
    document = extract_xlsx(xlsx_with_uncached_formula(), "test.xlsx", max_pages=10)

    assert document.pages[0].warnings == (DocumentWarning.MISSING_FORMULA_VALUES,)


def test_too_many_sheets_fails_with_file_too_large() -> None:
    with pytest.raises(AppError) as error:
        extract_xlsx(xlsx_with_sheets(3), "test.xlsx", max_pages=2)

    assert error.value.code is ErrorCode.FILE_TOO_LARGE
