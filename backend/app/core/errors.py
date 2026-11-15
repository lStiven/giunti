"""Application errors. They know nothing about HTTP (see `app.api.error_handlers`)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable error codes exposed to clients. Never rename one: clients depend on them."""

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INVALID_FILE = "INVALID_FILE"
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PROTECTED_FILE = "PROTECTED_FILE"
    NO_TEXT = "NO_TEXT"
    NO_ITEMS = "NO_ITEMS"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    NO_MODELS_AVAILABLE = "NO_MODELS_AVAILABLE"
    INVALID_LLM_RESPONSE = "INVALID_LLM_RESPONSE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_FORMAT: "Unsupported file format. Upload a PDF, DOCX or XLSX file.",
    ErrorCode.INVALID_FILE: "The file is damaged or is not a valid document.",
    ErrorCode.EMPTY_FILE: "The file is empty.",
    ErrorCode.FILE_TOO_LARGE: "The file exceeds the maximum allowed size.",
    ErrorCode.PROTECTED_FILE: "The file is password protected.",
    ErrorCode.NO_TEXT: "No readable content was found in the file.",
    ErrorCode.NO_ITEMS: "No questionnaire items were found in the file.",
    ErrorCode.LLM_UNAVAILABLE: "The language model is not available right now. Try again later.",
    ErrorCode.NO_MODELS_AVAILABLE: (
        "No language model is enabled on this server: no provider has an API key configured. "
        "Contact the service administrator."
    ),
    ErrorCode.INVALID_LLM_RESPONSE: "The language models did not return a valid extraction.",
    ErrorCode.UNAUTHENTICATED: "A valid API key is required.",
    ErrorCode.FORBIDDEN: "This API key is not allowed to perform this action.",
    ErrorCode.RATE_LIMITED: "Too many requests. Try again later.",
    ErrorCode.INVALID_REQUEST: "The request is not valid.",
    ErrorCode.NOT_FOUND: "The requested resource does not exist.",
    ErrorCode.INTERNAL_ERROR: "Unexpected internal error.",
}


class ErrorReason(StrEnum):
    """Why an error happened, when one code covers several situations that need different
    actions from the user (wait, retry, choose another model, change the file...).

    Stable like the codes: clients choose what to tell the user from them.
    """

    FILE_SIZE = "file_size"
    UNCOMPRESSED_SIZE = "uncompressed_size"
    TOO_MANY_PAGES = "too_many_pages"
    TOO_MANY_SHEETS = "too_many_sheets"
    SHEET_TOO_LARGE = "sheet_too_large"
    LEGACY_FORMAT = "legacy_format"
    MACROS = "macros"
    UNKNOWN_EXTENSION = "unknown_extension"
    EXTENSION_MISMATCH = "extension_mismatch"
    NOT_A_DOCUMENT = "not_a_document"
    DAMAGED = "damaged"
    CONVERSION_FAILED = "conversion_failed"
    MODEL_NOT_RESPONDING = "model_not_responding"
    QUOTA_EXHAUSTED = "quota_exhausted"
    MODEL_PAUSED = "model_paused"
    MODEL_MISCONFIGURED = "model_misconfigured"
    MODEL_REFUSED = "model_refused"
    OUTPUT_TOO_LONG = "output_too_long"
    INVALID_OUTPUT = "invalid_output"
    UNKNOWN_MODEL = "unknown_model"
    MODEL_WITHOUT_KEY = "model_without_key"
    DOCUMENT_TOO_LONG_FOR_MODEL = "document_too_long_for_model"
    MODEL_CANNOT_READ_IMAGES = "model_cannot_read_images"
    MODE_NOT_ALLOWED = "mode_not_allowed"
    INVALID_FIELDS = "invalid_fields"
    PER_MINUTE_LIMIT = "per_minute_limit"
    DAILY_LIMIT = "daily_limit"
    MISSING_KEY = "missing_key"
    INVALID_KEY = "invalid_key"


type ErrorDetails = dict[str, int | str]


class AppError(Exception):
    """An expected failure with a stable code and a message that is safe to show to clients.

    `reason` and `details` (limits, counts, the model id) let clients tell the user exactly what
    to do; `retry_after_s` says when trying again can work.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        retry_after_s: int | None = None,
        reason: ErrorReason | None = None,
        details: ErrorDetails | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.retry_after_s = retry_after_s
        self.reason = reason
        self.details: ErrorDetails = dict(details or {})
        super().__init__(f"{code}: {self.message}")
