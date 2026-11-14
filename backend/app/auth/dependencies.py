"""FastAPI dependencies for API key authentication and quotas.

`require_client` reads `X-API-Key`, resolves the client from the key, verifies the HMAC and
checks that the client is active. Missing, malformed, unknown and wrong keys produce the same
error (and take the same time) so client ids cannot be enumerated.

`require_extraction_quota` also consumes one unit of the client's quota: use it only on the
endpoints that call a model, which is what costs money.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Response, Security
from fastapi.security import APIKeyHeader

from app.auth.keys import client_id_of, hash_key, key_matches
from app.auth.rate_limit import Quota, RateLimiter
from app.auth.store import EnvKeyStore, KeyStore
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode

API_KEY_HEADER = "X-API-Key"
INVALID_KEY_MESSAGE = "The API key is not valid."
_DUMMY_KEY = "gk_dummy_key"

_api_key_header = APIKeyHeader(
    name=API_KEY_HEADER, auto_error=False, description="Client API key (gk_<client>_<secret>)"
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthenticatedClient:
    id: str
    quota: Quota


def get_key_store(settings: Annotated[Settings, Depends(get_settings)]) -> KeyStore:
    return EnvKeyStore(settings.api_keys)


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """One limiter per process, shared by every request."""
    return RateLimiter()


def require_client(
    api_key: Annotated[str | None, Security(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[KeyStore, Depends(get_key_store)],
) -> AuthenticatedClient:
    if not api_key:
        message = f"An API key is required in the {API_KEY_HEADER} header."
        raise AppError(ErrorCode.UNAUTHENTICATED, message)
    pepper = settings.api_key_pepper.get_secret_value()
    if not pepper:
        logger.error("api key pepper is not configured")
        raise AppError(ErrorCode.INTERNAL_ERROR, "Authentication is not configured on the server.")

    client_id = client_id_of(api_key)
    entry = store.find(client_id) if client_id else None
    if entry is None:
        # Same work as a wrong key, so the response time does not reveal existing clients.
        key_matches(api_key, hash_key(_DUMMY_KEY, pepper), pepper)
        logger.warning("authentication failed", extra={"reason": "unknown client"})
        raise AppError(ErrorCode.UNAUTHENTICATED, INVALID_KEY_MESSAGE)
    if not key_matches(api_key, entry.hash, pepper):
        logger.warning("authentication failed", extra={"reason": "wrong key", "client": entry.id})
        raise AppError(ErrorCode.UNAUTHENTICATED, INVALID_KEY_MESSAGE)
    if not entry.active:
        logger.warning("authentication failed", extra={"reason": "inactive", "client": entry.id})
        raise AppError(ErrorCode.FORBIDDEN, "This API key has been disabled.")

    return AuthenticatedClient(
        id=entry.id, quota=Quota(per_minute=entry.per_minute_limit, daily=entry.daily_limit)
    )


def require_extraction_quota(
    response: Response,
    client: Annotated[AuthenticatedClient, Depends(require_client)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> AuthenticatedClient:
    status = limiter.consume(client.id, client.quota)
    response.headers["X-RateLimit-Limit-Day"] = str(status.daily_limit)
    response.headers["X-RateLimit-Remaining-Day"] = str(status.daily_remaining)
    logger.info(
        "extraction quota consumed",
        extra={"client": client.id, "daily_remaining": status.daily_remaining},
    )
    return client
