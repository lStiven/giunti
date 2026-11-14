from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.documents.models import DocumentFormat
from app.documents.registry import detect_format, extract
from tests.base.office_builders import questionnaire_xlsx
from tests.base.pdf_builders import blank_pdf, text_pdf

_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")

SETTINGS = Settings(
    max_file_size_mb=1,
    max_pages=5,
    max_uncompressed_mb=1,
    render_dpi=72,
    render_max_px=600,
)


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _docx(extra: dict[str, bytes] | None = None) -> bytes:
    return _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w/>", **(extra or {})})


def _xlsx() -> bytes:
    return _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})


def _error_code(data: bytes, filename: str) -> ErrorCode:
    with pytest.raises(AppError) as error:
        extract(data, filename, SETTINGS)
    return error.value.code


def test_pdf_is_extracted() -> None:
    document = extract(text_pdf(), "Cuestionario.PDF", SETTINGS)

    assert document.document_format is DocumentFormat.PDF
    assert document.filename == "Cuestionario.PDF"
    assert len(document.pages) == 1


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (text_pdf(), DocumentFormat.PDF),
        (_docx(), DocumentFormat.DOCX),
        (_xlsx(), DocumentFormat.XLSX),
        (_zip({"other.txt": b"x"}), None),
        (b"plain text", None),
        (b"PK\x03\x04 broken zip", None),
    ],
)
def test_format_is_detected_from_content(data: bytes, expected: DocumentFormat | None) -> None:
    assert detect_format(data) is expected


def test_empty_file_fails_with_empty_file() -> None:
    assert _error_code(b"", "test.pdf") is ErrorCode.EMPTY_FILE


def test_file_over_size_limit_fails_with_file_too_large() -> None:
    assert _error_code(b"%PDF-" + b"0" * 1024 * 1024, "test.pdf") is ErrorCode.FILE_TOO_LARGE


@pytest.mark.parametrize("filename", ["test.doc", "test.xls", "test.docm", "test.xlsm", "test.txt"])
def test_legacy_macro_and_unknown_extensions_fail_with_unsupported_format(filename: str) -> None:
    assert _error_code(text_pdf(), filename) is ErrorCode.UNSUPPORTED_FORMAT


def test_extension_that_does_not_match_content_fails_with_invalid_file() -> None:
    assert _error_code(text_pdf(), "test.docx") is ErrorCode.INVALID_FILE


def test_unrecognised_content_fails_with_invalid_file() -> None:
    assert _error_code(b"just some text", "test.pdf") is ErrorCode.INVALID_FILE


def test_office_file_with_macros_fails_with_unsupported_format() -> None:
    data = _docx({"word/vbaProject.bin": b"macro"})

    assert _error_code(data, "test.docx") is ErrorCode.UNSUPPORTED_FORMAT


def test_office_file_that_expands_too_much_fails_with_file_too_large() -> None:
    data = _docx({"word/media/bomb.bin": b"0" * (2 * 1024 * 1024)})

    assert _error_code(data, "test.docx") is ErrorCode.FILE_TOO_LARGE


def test_xlsx_is_extracted() -> None:
    document = extract(questionnaire_xlsx(), "test.xlsx", SETTINGS)

    assert document.document_format is DocumentFormat.XLSX
    assert len(document.pages) == 2


def test_damaged_xlsx_fails_with_invalid_file() -> None:
    assert _error_code(_xlsx(), "test.xlsx") is ErrorCode.INVALID_FILE


@pytest.mark.parametrize("filename", ["test.docx", "test.xlsx"])
def test_password_protected_office_file_fails_with_protected_file(filename: str) -> None:
    data = _OLE_SIGNATURE + b"\0" * 64 + "EncryptedPackage".encode("utf-16-le")

    assert _error_code(data, filename) is ErrorCode.PROTECTED_FILE


def test_legacy_office_file_renamed_as_docx_fails_with_unsupported_format() -> None:
    data = _OLE_SIGNATURE + b"\0" * 64 + "WordDocument".encode("utf-16-le")

    assert _error_code(data, "test.docx") is ErrorCode.UNSUPPORTED_FORMAT


def test_document_without_text_or_figures_fails_with_no_text() -> None:
    assert _error_code(blank_pdf(), "test.pdf") is ErrorCode.NO_TEXT
