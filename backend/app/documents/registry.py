"""Single entry point: `extract(data, filename, settings) -> ExtractedDocument`.

Validates the upload, detects the real type from its content (and checks it against the
extension), dispatches to the matching extractor, and fails with NO_TEXT when nothing usable is
found. Extractors are CPU-bound and synchronous: call `extract` through `run_in_threadpool`.
"""

import logging
from collections.abc import Callable
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.documents.docx import LibreOfficeOptions, extract_docx
from app.documents.models import DocumentFormat, ExtractedDocument
from app.documents.pdf import extract_pdf
from app.documents.rendering import RenderOptions
from app.documents.security import (
    check_extension,
    check_not_ole_container,
    check_office_archive,
    check_size,
)
from app.documents.xlsx import extract_xlsx

type Extractor = Callable[[bytes, str, Settings], ExtractedDocument]

EXTENSIONS: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".xlsx": DocumentFormat.XLSX,
}

_PDF_SIGNATURE = b"%PDF-"
# The PDF header may come after a few bytes of junk, which readers tolerate.
_PDF_SIGNATURE_WINDOW = 1024
_ZIP_SIGNATURE = b"PK\x03\x04"
_OFFICE_MAIN_PARTS = {
    "word/document.xml": DocumentFormat.DOCX,
    "xl/workbook.xml": DocumentFormat.XLSX,
}

logger = logging.getLogger(__name__)


def _render_options(settings: Settings) -> RenderOptions:
    return RenderOptions(dpi=settings.render_dpi, max_px=settings.render_max_px)


def _extract_pdf(data: bytes, filename: str, settings: Settings) -> ExtractedDocument:
    render = _render_options(settings)
    return extract_pdf(data, filename, max_pages=settings.max_pages, render=render)


def _extract_docx(data: bytes, filename: str, settings: Settings) -> ExtractedDocument:
    libreoffice = LibreOfficeOptions(
        path=settings.libreoffice_path, timeout_s=settings.libreoffice_timeout_s
    )
    return extract_docx(
        data,
        filename,
        libreoffice=libreoffice,
        max_pages=settings.max_pages,
        render=_render_options(settings),
    )


def _extract_xlsx(data: bytes, filename: str, settings: Settings) -> ExtractedDocument:
    return extract_xlsx(data, filename, max_pages=settings.max_pages)


_EXTRACTORS: dict[DocumentFormat, Extractor] = {
    DocumentFormat.PDF: _extract_pdf,
    DocumentFormat.DOCX: _extract_docx,
    DocumentFormat.XLSX: _extract_xlsx,
}


def extract(data: bytes, filename: str, settings: Settings) -> ExtractedDocument:
    check_size(data, settings.max_file_size_mb)
    declared = _format_from_extension(filename)
    check_not_ole_container(data)
    detected = detect_format(data)
    if detected is None:
        raise AppError(ErrorCode.INVALID_FILE, "The file content is not a PDF, DOCX or XLSX.")
    if detected is not declared:
        message = f"The file extension does not match its content ({detected.upper()})."
        raise AppError(ErrorCode.INVALID_FILE, message)
    if detected is not DocumentFormat.PDF:
        check_office_archive(data, settings.max_uncompressed_mb)

    document = _EXTRACTORS[detected](data, filename, settings)
    if not any(page.char_count or page.figure_coverage for page in document.pages):
        raise AppError(ErrorCode.NO_TEXT)

    logger.info(
        "document extracted",
        extra={
            "document_format": document.document_format,
            "pages": len(document.pages),
            "requires_vision": document.requires_vision,
        },
    )
    return document


def detect_format(data: bytes) -> DocumentFormat | None:
    if _PDF_SIGNATURE in data[:_PDF_SIGNATURE_WINDOW]:
        return DocumentFormat.PDF
    if not data.startswith(_ZIP_SIGNATURE):
        return None
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except BadZipFile:
        return None
    return next((fmt for part, fmt in _OFFICE_MAIN_PARTS.items() if part in names), None)


def _format_from_extension(filename: str) -> DocumentFormat:
    check_extension(filename)
    suffix = PurePath(filename).suffix.lower()
    document_format = EXTENSIONS.get(suffix)
    if document_format is None:
        message = "Unsupported file format. Upload a PDF, DOCX or XLSX file."
        raise AppError(ErrorCode.UNSUPPORTED_FORMAT, message)
    return document_format
