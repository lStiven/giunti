"""Safety checks for untrusted uploads.

File size limit, maximum uncompressed size of DOCX/XLSX archives (zip bombs), and rejection of
macro-enabled and legacy Office formats.
"""

from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from app.core.errors import AppError, ErrorCode

BYTES_PER_MB = 1024 * 1024

LEGACY_EXTENSIONS = frozenset({".doc", ".xls", ".dot", ".xlt"})
MACRO_EXTENSIONS = frozenset({".docm", ".xlsm", ".dotm", ".xltm", ".xlsb"})

_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")


def check_size(data: bytes, max_size_mb: int) -> None:
    if not data:
        raise AppError(ErrorCode.EMPTY_FILE)
    if len(data) > max_size_mb * BYTES_PER_MB:
        message = f"The file exceeds the maximum size of {max_size_mb} MB."
        raise AppError(ErrorCode.FILE_TOO_LARGE, message)


def check_extension(filename: str) -> None:
    suffix = PurePath(filename).suffix.lower()
    if suffix in LEGACY_EXTENSIONS:
        message = f"Legacy {suffix} files are not supported. Save the file as .docx or .xlsx."
        raise AppError(ErrorCode.UNSUPPORTED_FORMAT, message)
    if suffix in MACRO_EXTENSIONS:
        message = f"Macro-enabled {suffix} files are not supported. Save it without macros."
        raise AppError(ErrorCode.UNSUPPORTED_FORMAT, message)


def check_not_ole_container(data: bytes) -> None:
    """Rejects OLE containers: password-protected DOCX/XLSX and legacy .doc/.xls files.

    Office stores encrypted DOCX/XLSX inside an OLE container with an `EncryptedPackage` stream
    instead of a zip archive, so they would otherwise look like invalid files.
    """
    if not data.startswith(_OLE_SIGNATURE):
        return
    if _ENCRYPTED_PACKAGE in data:
        raise AppError(ErrorCode.PROTECTED_FILE)
    message = "Legacy Word and Excel files are not supported. Save the file as .docx or .xlsx."
    raise AppError(ErrorCode.UNSUPPORTED_FORMAT, message)


def check_office_archive(data: bytes, max_uncompressed_mb: int) -> None:
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
    except BadZipFile as exc:
        raise AppError(ErrorCode.INVALID_FILE) from exc

    if sum(entry.file_size for entry in entries) > max_uncompressed_mb * BYTES_PER_MB:
        message = f"The uncompressed file exceeds {max_uncompressed_mb} MB."
        raise AppError(ErrorCode.FILE_TOO_LARGE, message)
    if any(entry.filename.lower().endswith("vbaproject.bin") for entry in entries):
        message = "Files with macros are not supported. Save the file without macros."
        raise AppError(ErrorCode.UNSUPPORTED_FORMAT, message)
