import shutil
from pathlib import Path

import pytest

from app.core.errors import AppError, ErrorCode
from app.documents.docx import LibreOfficeOptions, convert_to_pdf, extract_docx
from app.documents.models import DocumentFormat, PageSource
from app.documents.rendering import RenderOptions
from tests.base.office_builders import questionnaire_docx

RENDER = RenderOptions(dpi=72, max_px=800)

requires_libreoffice = pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice is not installed"
)


def _fake_libreoffice(tmp_path: Path, script: str) -> LibreOfficeOptions:
    executable = tmp_path / "fake-soffice"
    executable.write_text(f"#!/bin/sh\n{script}\n")
    executable.chmod(0o755)
    return LibreOfficeOptions(path=str(executable), timeout_s=1)


def _conversion_error(data: bytes, libreoffice: LibreOfficeOptions) -> AppError:
    with pytest.raises(AppError) as error:
        convert_to_pdf(data, libreoffice)
    return error.value


@requires_libreoffice
def test_docx_is_rendered_keeping_numbering_and_answer_marks() -> None:
    libreoffice = LibreOfficeOptions(path="soffice", timeout_s=60)

    document = extract_docx(
        questionnaire_docx(), "test.docx", libreoffice=libreoffice, max_pages=5, render=RENDER
    )

    assert document.document_format is DocumentFormat.DOCX
    page = document.pages[0]
    lines = page.text.splitlines()
    assert page.source is PageSource.TEXT_LAYER
    assert page.image_png is not None
    assert "1. Quale e la capitale d'Italia?" in lines
    assert "2. Il fiume piu lungo d'Italia?" in lines
    assert "**Roma**" in lines
    assert "<u>Napoli</u>" in lines
    assert "==Torino==" in lines
    assert "☐ Vero ☒ Falso" in lines
    assert "| Mai | A volte | Sempre |" in lines


def test_missing_libreoffice_fails_with_internal_error(tmp_path: Path) -> None:
    libreoffice = LibreOfficeOptions(path=str(tmp_path / "missing"), timeout_s=1)

    assert _conversion_error(b"docx", libreoffice).code is ErrorCode.INTERNAL_ERROR


def test_failed_conversion_fails_with_invalid_file(tmp_path: Path) -> None:
    libreoffice = _fake_libreoffice(tmp_path, "exit 1")

    assert _conversion_error(b"docx", libreoffice).code is ErrorCode.INVALID_FILE


def test_conversion_without_output_fails_with_invalid_file(tmp_path: Path) -> None:
    libreoffice = _fake_libreoffice(tmp_path, "exit 0")

    assert _conversion_error(b"docx", libreoffice).code is ErrorCode.INVALID_FILE


def test_slow_conversion_is_stopped_and_fails_with_invalid_file(tmp_path: Path) -> None:
    libreoffice = _fake_libreoffice(tmp_path, "sleep 30")

    error = _conversion_error(b"docx", libreoffice)

    assert error.code is ErrorCode.INVALID_FILE
    assert "too long" in error.message
