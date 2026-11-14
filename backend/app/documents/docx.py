"""DOCX extractor: converts to PDF with headless LibreOffice and delegates to the PDF extractor.

Rendering makes automatic numbering, text boxes, drawn shapes and equations visible without
format-specific code.
"""

import logging
import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from app.core.errors import AppError, ErrorCode, ErrorReason
from app.documents.models import DocumentFormat, ExtractedDocument
from app.documents.pdf import extract_pdf
from app.documents.rendering import RenderOptions

CONVERSION_FAILED = "The DOCX file could not be converted."

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LibreOfficeOptions:
    path: str
    timeout_s: int


def extract_docx(
    data: bytes,
    filename: str,
    *,
    libreoffice: LibreOfficeOptions,
    max_pages: int,
    render: RenderOptions,
) -> ExtractedDocument:
    pdf = convert_to_pdf(data, libreoffice)
    document = extract_pdf(pdf, filename, max_pages=max_pages, render=render)
    return replace(document, document_format=DocumentFormat.DOCX)


def convert_to_pdf(data: bytes, libreoffice: LibreOfficeOptions) -> bytes:
    with tempfile.TemporaryDirectory(prefix="docx-") as workdir:
        work = Path(workdir)
        # The client's filename never reaches the command line.
        source = work / "document.docx"
        source.write_bytes(data)
        command = [
            libreoffice.path,
            "--headless",
            "--norestore",
            "--nolockcheck",
            # A private profile per conversion lets several conversions run in parallel.
            f"-env:UserInstallation={(work / 'profile').as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work),
            str(source),
        ]
        _run(command, libreoffice.timeout_s)
        output = work / "document.pdf"
        if not output.is_file() or output.stat().st_size == 0:
            raise AppError(
                ErrorCode.INVALID_FILE, CONVERSION_FAILED, reason=ErrorReason.CONVERSION_FAILED
            )
        return output.read_bytes()


def _run(command: list[str], timeout_s: int) -> None:
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed arguments, no shell, private temp files
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        logger.exception("libreoffice could not be started", extra={"path": command[0]})
        message = "DOCX conversion is not available on this server."
        raise AppError(ErrorCode.INTERNAL_ERROR, message) from exc

    try:
        _, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        # `soffice` is a launcher: killing only it would leave the real converter running.
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        logger.warning("libreoffice conversion timed out", extra={"timeout_s": timeout_s})
        message = "The DOCX file took too long to convert. Try a smaller or simpler file."
        raise AppError(
            ErrorCode.INVALID_FILE, message, reason=ErrorReason.CONVERSION_FAILED
        ) from exc

    if process.returncode != 0:
        logger.warning(
            "libreoffice conversion failed",
            extra={"returncode": process.returncode, "stderr": stderr.decode(errors="replace")},
        )
        raise AppError(
            ErrorCode.INVALID_FILE, CONVERSION_FAILED, reason=ErrorReason.CONVERSION_FAILED
        )
