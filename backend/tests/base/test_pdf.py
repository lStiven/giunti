from io import BytesIO

import pytest
from PIL import Image
from reportlab.lib.pdfencrypt import StandardEncryption

from app.core.errors import AppError, ErrorCode
from app.documents.models import DocumentPage, DocumentWarning, PageSource
from app.documents.pdf import FIGURE_MARK, extract_pdf
from app.documents.rendering import RenderOptions
from tests.base.pdf_builders import questionnaire_pdf, scanned_pdf, text_pdf

RENDER = RenderOptions(dpi=72, max_px=800)


def _single_page(data: bytes) -> DocumentPage:
    document = extract_pdf(data, "test.pdf", max_pages=10, render=RENDER)
    assert len(document.pages) == 1
    return document.pages[0]


@pytest.fixture(scope="module")
def questionnaire_lines() -> list[str]:
    return _single_page(questionnaire_pdf()).text.splitlines()


def test_plain_text_has_no_marks(questionnaire_lines: list[str]) -> None:
    assert questionnaire_lines[0] == "1. Quale e la capitale d'Italia?"
    assert "A) Milano" in questionnaire_lines


def test_bold_font_is_marked(questionnaire_lines: list[str]) -> None:
    assert "**B) Roma**" in questionnaire_lines


def test_line_under_a_word_is_marked_as_underline(questionnaire_lines: list[str]) -> None:
    assert "<u>C) Napoli</u>" in questionnaire_lines


def test_coloured_rectangle_behind_a_word_is_marked_as_highlight(
    questionnaire_lines: list[str],
) -> None:
    assert "==D) Torino==" in questionnaire_lines


def test_page_wide_rule_below_a_word_is_not_an_underline(questionnaire_lines: list[str]) -> None:
    assert "■ Vero" in questionnaire_lines


def test_word_hyphenated_at_line_end_is_joined(questionnaire_lines: list[str]) -> None:
    assert "2. Questa domanda e molto lunga e continua." in questionnaire_lines


def test_table_becomes_markdown_table(questionnaire_lines: list[str]) -> None:
    start = questionnaire_lines.index("| Mai | Sempre |")

    assert questionnaire_lines[start : start + 3] == [
        "| Mai | Sempre |",
        "| --- | --- |",
        "| 0 | 1 |",
    ]


def test_vector_drawing_becomes_figure_marker_after_the_text(
    questionnaire_lines: list[str],
) -> None:
    assert questionnaire_lines[-1] == FIGURE_MARK


def test_page_with_text_layer_is_read_from_text() -> None:
    page = _single_page(questionnaire_pdf())

    assert page.source is PageSource.TEXT_LAYER
    assert page.warnings == ()
    assert 0 < page.figure_coverage < 1


def test_scanned_page_must_be_read_from_its_image() -> None:
    page = _single_page(scanned_pdf())

    assert page.source is PageSource.IMAGE_ONLY
    assert page.warnings == (DocumentWarning.NO_TEXT_LAYER,)
    assert page.char_count == 0
    assert page.figure_coverage == pytest.approx(1.0)
    assert page.text == FIGURE_MARK


def test_every_page_gets_a_png_image_within_the_size_cap() -> None:
    page = _single_page(text_pdf())

    assert page.image_png is not None
    image = Image.open(BytesIO(page.image_png))
    assert image.format == "PNG"
    assert max(image.size) <= RENDER.max_px


def test_pages_are_numbered_from_one() -> None:
    document = extract_pdf(text_pdf(pages=3), "test.pdf", max_pages=10, render=RENDER)

    assert [page.number for page in document.pages] == [1, 2, 3]
    assert document.pages[2].text == "Pagina 3: indica quanto sei d'accordo."


def test_too_many_pages_fails_with_file_too_large() -> None:
    with pytest.raises(AppError) as error:
        extract_pdf(text_pdf(pages=3), "test.pdf", max_pages=2, render=RENDER)

    assert error.value.code is ErrorCode.FILE_TOO_LARGE


def test_password_protected_pdf_fails_with_protected_file() -> None:
    data = questionnaire_pdf(encrypt=StandardEncryption("secret"))

    with pytest.raises(AppError) as error:
        extract_pdf(data, "test.pdf", max_pages=10, render=RENDER)

    assert error.value.code is ErrorCode.PROTECTED_FILE


def test_pdf_with_only_an_owner_password_can_be_read() -> None:
    data = questionnaire_pdf(encrypt=StandardEncryption("", ownerPassword="owner"))

    page = _single_page(data)

    assert page.text.startswith("1. Quale")


def test_corrupted_pdf_fails_with_invalid_file() -> None:
    with pytest.raises(AppError) as error:
        extract_pdf(b"%PDF-1.7 not really a pdf", "test.pdf", max_pages=10, render=RENDER)

    assert error.value.code is ErrorCode.INVALID_FILE
