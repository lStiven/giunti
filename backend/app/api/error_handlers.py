"""Maps application errors to HTTP responses shaped as
`{"error": {"code": ..., "message": ..., "request_id": ...}}`.

Every failure uses this shape, including unknown routes, invalid requests and unexpected
exceptions, so clients only need to handle one error format.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware import REQUEST_ID_HEADER
from app.core.errors import DEFAULT_MESSAGES, AppError, ErrorCode

HTTP_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_FORMAT: 415,
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.INVALID_FILE: 422,
    ErrorCode.EMPTY_FILE: 422,
    ErrorCode.PROTECTED_FILE: 422,
    ErrorCode.NO_TEXT: 422,
    ErrorCode.NO_ITEMS: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.LLM_UNAVAILABLE: 502,
    ErrorCode.INVALID_LLM_RESPONSE: 502,
}

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    request_id: str | None


class ErrorResponse(BaseModel):
    """Body of every error response."""

    error: ErrorDetail


def _request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None


def _error_response(
    request: Request,
    code: ErrorCode,
    message: str,
    *,
    status_code: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, request_id=request_id))
    response_headers = dict(headers or {})
    if request_id is not None:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code or HTTP_STATUS_BY_CODE[code],
        content=body.model_dump(mode="json"),
        headers=response_headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info("request failed", extra={"error_code": exc.code})
        headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s is not None else None
        return _error_response(request, exc.code, exc.message, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Only field locations are reported: the rejected input could contain document content.
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        message = f"{DEFAULT_MESSAGES[ErrorCode.INVALID_REQUEST]} Check: {', '.join(fields)}."
        return _error_response(request, ErrorCode.INVALID_REQUEST, message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        is_not_found = exc.status_code == HTTPStatus.NOT_FOUND
        code = ErrorCode.NOT_FOUND if is_not_found else ErrorCode.INVALID_REQUEST
        return _error_response(
            request,
            code,
            DEFAULT_MESSAGES[code],
            status_code=exc.status_code,
            headers=dict(exc.headers or {}),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=exc)
        return _error_response(
            request, ErrorCode.INTERNAL_ERROR, DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR]
        )
