"""Request middleware.

Assigns a request id (or reuses the `X-Request-ID` header), exposes it in
`app.core.logging.request_id_var`, in `request.state.request_id` and in the response headers,
and logs each request's duration.
"""

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"

# Incoming ids end up in logs and headers, so only short, plain tokens are trusted.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

logger = logging.getLogger(__name__)


def _request_id_from(scope: Scope) -> str:
    incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
    if incoming is not None and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid4().hex


class RequestContextMiddleware:
    """Pure ASGI middleware, so it also wraps streaming responses and exception handlers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from(scope)
        # The 500 handler runs outside this middleware, after the context variable is reset.
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            request_id_var.reset(token)
