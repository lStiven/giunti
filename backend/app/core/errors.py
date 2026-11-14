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


class AppError(Exception):
    """An expected failure with a stable code and a message that is safe to show to clients."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        retry_after_s: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.retry_after_s = retry_after_s
        super().__init__(f"{code}: {self.message}")
