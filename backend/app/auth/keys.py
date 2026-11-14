"""API key generation and hashing.

Keys look like `gk_<client>_<secret>` with a 32-byte random secret. They are stored as
HMAC-SHA256 digests keyed with `API_KEY_PEPPER` and compared with `hmac.compare_digest`.
A slow password hash is unnecessary because keys are high-entropy random values.
"""

import hashlib
import hmac
import re
import secrets

from app.core.config import CLIENT_ID_PATTERN

KEY_PREFIX = "gk"
SECRET_BYTES = 32
_CLIENT_ID = re.compile(CLIENT_ID_PATTERN)


def generate_key(client_id: str) -> str:
    if not _CLIENT_ID.match(client_id):
        message = f"Invalid client id '{client_id}': use lowercase letters, digits and '-'"
        raise ValueError(message)
    return f"{KEY_PREFIX}_{client_id}_{secrets.token_urlsafe(SECRET_BYTES)}"


def client_id_of(key: str) -> str | None:
    """The client id embedded in the key, or None when the key is malformed."""
    prefix, _, rest = key.partition("_")
    client_id, separator, secret = rest.partition("_")
    if prefix != KEY_PREFIX or not separator or not secret or not _CLIENT_ID.match(client_id):
        return None
    return client_id


def hash_key(key: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


def key_matches(key: str, expected_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_key(key, pepper), expected_hash)
