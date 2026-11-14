"""Authorized clients: lookup for authentication and management for administrators.

`KeyStore` is what authentication needs; `ClientRepository` implements it on the database and
adds the operations of the admin panel and the admin command.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import ClientRow

MAX_CLIENT_ID_LENGTH = 32
_NOT_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class ClientRecord:
    id: str
    name: str
    key_hash: str
    active: bool
    is_admin: bool
    per_minute_limit: int
    daily_limit: int
    created_at: datetime
    key_created_at: datetime
    last_used_at: datetime | None


class KeyStore(Protocol):
    def find(self, client_id: str) -> ClientRecord | None:
        """The client, or None when it does not exist."""
        ...


@dataclass(frozen=True, slots=True)
class NewClient:
    name: str
    key_hash: str
    per_minute_limit: int
    daily_limit: int
    is_admin: bool = False
    client_id: str | None = None
    """Generated from the name when not given."""


class ClientRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, client_id: str) -> ClientRecord | None:
        row = self._session.get(ClientRow, client_id)
        return _record(row) if row else None

    def list_all(self) -> list[ClientRecord]:
        rows = self._session.scalars(select(ClientRow).order_by(ClientRow.created_at.desc()))
        return [_record(row) for row in rows]

    def available_id(self, name: str) -> str:
        """A free client id derived from the name: "Colegio San José" → "colegio-san-jose"."""
        base = slugify(name) or "cliente"
        candidate, suffix = base, 2
        while self._session.get(ClientRow, candidate) is not None:
            tail = f"-{suffix}"
            candidate = f"{base[: MAX_CLIENT_ID_LENGTH - len(tail)]}{tail}"
            suffix += 1
        return candidate

    def create(self, client: NewClient) -> ClientRecord:
        now = datetime.now(UTC)
        row = ClientRow(
            id=client.client_id or self.available_id(client.name),
            name=client.name,
            key_hash=client.key_hash,
            active=True,
            is_admin=client.is_admin,
            per_minute_limit=client.per_minute_limit,
            daily_limit=client.daily_limit,
            created_at=now,
            key_created_at=now,
            last_used_at=None,
        )
        self._session.add(row)
        self._session.commit()
        return _record(row)

    def update(
        self,
        client_id: str,
        *,
        name: str | None = None,
        active: bool | None = None,
        per_minute_limit: int | None = None,
        daily_limit: int | None = None,
    ) -> ClientRecord | None:
        row = self._session.get(ClientRow, client_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if active is not None:
            row.active = active
        if per_minute_limit is not None:
            row.per_minute_limit = per_minute_limit
        if daily_limit is not None:
            row.daily_limit = daily_limit
        self._session.commit()
        return _record(row)

    def replace_key(self, client_id: str, key_hash: str) -> ClientRecord | None:
        row = self._session.get(ClientRow, client_id)
        if row is None:
            return None
        row.key_hash = key_hash
        row.key_created_at = datetime.now(UTC)
        self._session.commit()
        return _record(row)

    def mark_used(self, client_id: str) -> None:
        row = self._session.get(ClientRow, client_id)
        if row is not None:
            row.last_used_at = datetime.now(UTC)
            self._session.commit()


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _NOT_SLUG.sub("-", ascii_name.lower()).strip("-")[:MAX_CLIENT_ID_LENGTH].strip("-")


def _record(row: ClientRow) -> ClientRecord:
    return ClientRecord(
        id=row.id,
        name=row.name,
        key_hash=row.key_hash,
        active=row.active,
        is_admin=row.is_admin,
        per_minute_limit=row.per_minute_limit,
        daily_limit=row.daily_limit,
        created_at=_utc(row.created_at),
        key_created_at=_utc(row.key_created_at),
        last_used_at=_utc(row.last_used_at) if row.last_used_at else None,
    )


def _utc(moment: datetime) -> datetime:
    # SQLite drops the time zone; every stored moment is UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
