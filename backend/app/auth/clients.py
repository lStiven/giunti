"""Issuing client keys, shared by the admin panel and the admin command.

A key is shown only once, when it is created or replaced: only its HMAC is stored. Together
with it goes an invitation link that signs the person in with one click; the key travels in
the URL fragment (`#clave=`), which browsers never send to the server.
"""

from dataclasses import dataclass

from app.auth.keys import generate_key, hash_key
from app.auth.store import ClientRecord, ClientRepository, NewClient
from app.core.config import Settings

INVITE_FRAGMENT = "clave"


@dataclass(frozen=True, slots=True)
class IssuedKey:
    client: ClientRecord
    api_key: str
    invite_url: str


@dataclass(frozen=True, slots=True)
class ClientLimits:
    per_minute: int
    daily: int


def issue_client(  # noqa: PLR0913 - every argument is a property of the new client
    clients: ClientRepository,
    settings: Settings,
    *,
    name: str,
    limits: ClientLimits,
    is_admin: bool = False,
    allow_precise: bool = False,
    client_id: str | None = None,
) -> IssuedKey:
    client_id = client_id or clients.available_id(name)
    api_key = generate_key(client_id)
    record = clients.create(
        NewClient(
            name=name,
            key_hash=hash_key(api_key, _pepper(settings)),
            per_minute_limit=limits.per_minute,
            daily_limit=limits.daily,
            is_admin=is_admin,
            allow_precise=allow_precise,
            client_id=client_id,
        )
    )
    return IssuedKey(record, api_key, invite_url(settings, api_key, admin=is_admin))


def replace_key(clients: ClientRepository, settings: Settings, client_id: str) -> IssuedKey | None:
    """A new key for the client; the previous one stops working immediately."""
    api_key = generate_key(client_id)
    record = clients.replace_key(client_id, hash_key(api_key, _pepper(settings)))
    if record is None:
        return None
    return IssuedKey(record, api_key, invite_url(settings, api_key, admin=record.is_admin))


def invite_url(settings: Settings, api_key: str, *, admin: bool = False) -> str:
    path = "/admin" if admin else "/"
    return f"{settings.public_app_url.rstrip('/')}{path}#{INVITE_FRAGMENT}={api_key}"


def _pepper(settings: Settings) -> str:
    pepper = settings.api_key_pepper.get_secret_value()
    if not pepper:
        message = "API_KEY_PEPPER is empty: set it before creating keys."
        raise ValueError(message)
    return pepper
