"""Authorized client lookup.

`KeyStore` protocol with an `EnvKeyStore` implementation backed by `settings.api_keys`.
A database-backed implementation can replace it when the number of clients grows.
"""

from collections.abc import Iterable
from typing import Protocol

from app.core.config import ApiKeyEntry


class KeyStore(Protocol):
    def find(self, client_id: str) -> ApiKeyEntry | None:
        """The client's entry, or None when the client does not exist."""
        ...


class EnvKeyStore:
    def __init__(self, entries: Iterable[ApiKeyEntry]) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def find(self, client_id: str) -> ApiKeyEntry | None:
        return self._entries.get(client_id)
