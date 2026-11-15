"""`/api/v1/admin`: the admin panel's API. Every endpoint needs an administrator key.

Administrators manage clients: create them (getting a key and an invitation link once), change
their name and limits, deactivate them, replace their key and delete them. Administrators
themselves are created and deleted only with the admin commands, so nobody can grant or remove
admin rights from the web.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field, StringConstraints

from app.auth.clients import ClientLimits, IssuedKey, issue_client, replace_key
from app.auth.dependencies import (
    AuthenticatedClient,
    TodayUsage,
    get_client_repository,
    get_today_usage,
    require_admin,
)
from app.auth.store import ClientRecord, ClientRepository
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode

MAX_DAILY_LIMIT = 10_000
MAX_PER_MINUTE_LIMIT = 600

type ClientName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class ClientView(BaseModel):
    id: str
    name: str
    active: bool
    is_admin: bool
    allow_precise: bool
    per_minute_limit: int
    daily_limit: int
    used_today: int
    created_at: datetime
    key_created_at: datetime
    last_used_at: datetime | None


class IssuedKeyView(BaseModel):
    client: ClientView
    api_key: str
    """Shown only in this response: the server keeps only its hash."""

    invite_url: str


class CreateClientRequest(BaseModel):
    name: ClientName
    daily_limit: int = Field(default=100, ge=1, le=MAX_DAILY_LIMIT)
    per_minute_limit: int = Field(default=10, ge=1, le=MAX_PER_MINUTE_LIMIT)
    allow_precise: bool = False
    """Fast mode only unless the administrator allows the precise one."""


class UpdateClientRequest(BaseModel):
    name: ClientName | None = None
    active: bool | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=MAX_DAILY_LIMIT)
    per_minute_limit: int | None = Field(default=None, ge=1, le=MAX_PER_MINUTE_LIMIT)
    allow_precise: bool | None = None


type Admin = Annotated[AuthenticatedClient, Depends(require_admin)]
type Clients = Annotated[ClientRepository, Depends(get_client_repository)]
type Today = Annotated[TodayUsage, Depends(get_today_usage)]
type CurrentSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/clients")
def list_clients(_: Admin, clients: Clients, today: Today) -> list[ClientView]:
    used_today = today.by_client()
    return [_view(client, used_today.get(client.id, 0)) for client in clients.list_all()]


@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    request: CreateClientRequest,
    _: Admin,
    clients: Clients,
    settings: CurrentSettings,
) -> IssuedKeyView:
    limits = ClientLimits(per_minute=request.per_minute_limit, daily=request.daily_limit)
    issued = issue_client(
        clients,
        settings,
        name=request.name,
        limits=limits,
        allow_precise=request.allow_precise,
    )
    return _issued_view(issued, used_today=0)


@router.patch("/clients/{client_id}")
def update_client(
    client_id: str,
    request: UpdateClientRequest,
    admin: Admin,
    clients: Clients,
    today: Today,
) -> ClientView:
    if client_id == admin.id and request.active is False:
        raise AppError(ErrorCode.INVALID_REQUEST, "You cannot deactivate your own key.")
    updated = clients.update(
        client_id,
        name=request.name,
        active=request.active,
        per_minute_limit=request.per_minute_limit,
        daily_limit=request.daily_limit,
        allow_precise=request.allow_precise,
    )
    if updated is None:
        raise _client_not_found(client_id)
    return _view(updated, today.of(client_id))


@router.post("/clients/{client_id}/key")
def replace_client_key(
    client_id: str,
    admin: Admin,
    clients: Clients,
    today: Today,
    settings: CurrentSettings,
) -> IssuedKeyView:
    if client_id == admin.id:
        message = "Replace your own key with the admin command, not from the panel."
        raise AppError(ErrorCode.INVALID_REQUEST, message)
    issued = replace_key(clients, settings, client_id)
    if issued is None:
        raise _client_not_found(client_id)
    return _issued_view(issued, today.of(client_id))


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: str, _: Admin, clients: Clients) -> Response:
    client = clients.find(client_id)
    if client is None:
        raise _client_not_found(client_id)
    if client.is_admin:
        message = "Administrators are deleted with the admin command, not from the panel."
        raise AppError(ErrorCode.INVALID_REQUEST, message)
    clients.delete(client_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _view(client: ClientRecord, used_today: int) -> ClientView:
    return ClientView(
        id=client.id,
        name=client.name,
        active=client.active,
        is_admin=client.is_admin,
        allow_precise=client.allow_precise,
        per_minute_limit=client.per_minute_limit,
        daily_limit=client.daily_limit,
        used_today=used_today,
        created_at=client.created_at,
        key_created_at=client.key_created_at,
        last_used_at=client.last_used_at,
    )


def _issued_view(issued: IssuedKey, used_today: int) -> IssuedKeyView:
    return IssuedKeyView(
        client=_view(issued.client, used_today),
        api_key=issued.api_key,
        invite_url=issued.invite_url,
    )


def _client_not_found(client_id: str) -> AppError:
    return AppError(ErrorCode.NOT_FOUND, f"The client '{client_id}' does not exist.")
