from collections.abc import Iterator
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from app.auth.clients import ClientLimits, issue_client
from app.auth.dependencies import get_rate_limiter
from app.auth.rate_limit import RateLimiter
from app.auth.store import ClientRepository, UsageRepository
from app.core.config import LLMCatalog, Settings, get_settings
from app.main import app

SETTINGS = Settings(
    api_key_pepper=SecretStr("p" * 40),
    public_app_url="https://app.example/",
    gemini_api_key=SecretStr("g"),
    llm_catalog=LLMCatalog.model_validate(
        {
            "default_model": "flash",
            "providers": {"gemini": {"label": "Gemini", "description": "d"}},
            "models": [{"id": "flash", "model": "gemini/flash", "fast_reasoning_effort": "low"}],
        }
    ),
)
LIMITS = ClientLimits(per_minute=10, daily=100)


class ApiResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...  # noqa: ANN401 - raw JSON body


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter()


@pytest.fixture
def keys(database: sessionmaker[Session], limiter: RateLimiter) -> Iterator[dict[str, str]]:
    with database() as session:
        clients = ClientRepository(session)
        admin = issue_client(clients, SETTINGS, name="Admin", limits=LIMITS, is_admin=True)
        school = issue_client(clients, SETTINGS, name="Colegio San José", limits=LIMITS)
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    yield {"admin": admin.api_key, "school": school.api_key}
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_rate_limiter, None)


def _call(
    method: str, path: str, key: str | None, body: dict[str, Any] | None = None
) -> ApiResponse:
    headers = {"X-API-Key": key} if key else {}
    return TestClient(app).request(method, f"/api/v1/admin{path}", headers=headers, json=body)


def _models_status(key: str) -> int:
    return TestClient(app).get("/api/v1/models", headers={"X-API-Key": key}).status_code


@pytest.mark.usefixtures("keys")
def test_admin_panel_needs_a_key() -> None:
    assert _call("GET", "/clients", None).status_code == 401


def test_client_keys_cannot_use_the_admin_panel(keys: dict[str, str]) -> None:
    response = _call("GET", "/clients", keys["school"])

    assert response.status_code == 403
    assert "administrator" in response.json()["error"]["message"]


def test_admin_lists_clients_with_todays_usage(
    keys: dict[str, str], limiter: RateLimiter, database: sessionmaker[Session]
) -> None:
    with database() as session:
        UsageRepository(session).try_increment("colegio-san-jose", limiter.today(), 100)

    clients = {client["id"]: client for client in _call("GET", "/clients", keys["admin"]).json()}

    assert set(clients) == {"admin", "colegio-san-jose"}
    assert clients["colegio-san-jose"]["used_today"] == 1
    assert clients["admin"]["is_admin"] is True


def test_created_client_gets_a_working_key_and_an_invitation_link(keys: dict[str, str]) -> None:
    response = _call(
        "POST", "/clients", keys["admin"], {"name": "  Liceo Nº 5  ", "daily_limit": 30}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["client"]["id"] == "liceo-no-5"
    assert body["client"]["name"] == "Liceo Nº 5"
    assert body["client"]["daily_limit"] == 30
    assert body["invite_url"] == f"https://app.example/#clave={body['api_key']}"
    assert _models_status(body["api_key"]) == 200


def test_clients_with_the_same_name_get_distinct_ids(keys: dict[str, str]) -> None:
    created = _call("POST", "/clients", keys["admin"], {"name": "Colegio San José"}).json()

    assert created["client"]["id"] == "colegio-san-jose-2"


@pytest.mark.parametrize(
    "body",
    [{"name": "   "}, {"name": "x", "daily_limit": 0}, {"name": "x", "per_minute_limit": 601}],
)
def test_invalid_new_clients_are_rejected(keys: dict[str, str], body: dict[str, Any]) -> None:
    assert _call("POST", "/clients", keys["admin"], body).status_code == 422


def test_deactivated_client_loses_access_until_reactivated(keys: dict[str, str]) -> None:
    _call("PATCH", "/clients/colegio-san-jose", keys["admin"], {"active": False})
    assert _models_status(keys["school"]) == 403

    _call("PATCH", "/clients/colegio-san-jose", keys["admin"], {"active": True})
    assert _models_status(keys["school"]) == 200


def test_limits_and_name_can_be_changed(keys: dict[str, str]) -> None:
    response = _call(
        "PATCH", "/clients/colegio-san-jose", keys["admin"], {"daily_limit": 5, "name": "CSJ"}
    )

    assert response.json()["daily_limit"] == 5
    assert response.json()["name"] == "CSJ"


def test_new_clients_get_only_the_fast_mode_unless_the_admin_allows_precise(
    keys: dict[str, str],
) -> None:
    fast = _call("POST", "/clients", keys["admin"], {"name": "Solo rapido"}).json()
    precise = _call(
        "POST", "/clients", keys["admin"], {"name": "Con preciso", "allow_precise": True}
    ).json()

    assert fast["client"]["allow_precise"] is False
    assert precise["client"]["allow_precise"] is True


def test_the_precise_mode_can_be_granted_and_removed(keys: dict[str, str]) -> None:
    granted = _call("PATCH", "/clients/colegio-san-jose", keys["admin"], {"allow_precise": True})
    removed = _call("PATCH", "/clients/colegio-san-jose", keys["admin"], {"allow_precise": False})

    assert granted.json()["allow_precise"] is True
    assert removed.json()["allow_precise"] is False
    assert removed.json()["daily_limit"] == LIMITS.daily


def test_admins_cannot_deactivate_themselves(keys: dict[str, str]) -> None:
    response = _call("PATCH", "/clients/admin", keys["admin"], {"active": False})

    assert response.status_code == 422
    assert _models_status(keys["admin"]) == 200


def test_replacing_a_key_invalidates_the_previous_one(keys: dict[str, str]) -> None:
    response = _call("POST", "/clients/colegio-san-jose/key", keys["admin"])

    assert _models_status(keys["school"]) == 401
    assert _models_status(response.json()["api_key"]) == 200


def test_admins_cannot_replace_their_own_key_from_the_panel(keys: dict[str, str]) -> None:
    assert _call("POST", "/clients/admin/key", keys["admin"]).status_code == 422


def test_deleting_a_client_removes_it_with_its_key_and_usage(
    keys: dict[str, str], limiter: RateLimiter, database: sessionmaker[Session]
) -> None:
    with database() as session:
        UsageRepository(session).try_increment("colegio-san-jose", limiter.today(), 100)

    response = _call("DELETE", "/clients/colegio-san-jose", keys["admin"])

    assert response.status_code == 204
    assert _models_status(keys["school"]) == 401
    listed = [client["id"] for client in _call("GET", "/clients", keys["admin"]).json()]
    assert listed == ["admin"]
    with database() as session:
        assert UsageRepository(session).counts_on(limiter.today()) == {}


def test_administrators_cannot_be_deleted_from_the_panel(keys: dict[str, str]) -> None:
    response = _call("DELETE", "/clients/admin", keys["admin"])

    assert response.status_code == 422
    assert _models_status(keys["admin"]) == 200


def test_clients_cannot_delete_other_clients(keys: dict[str, str]) -> None:
    assert _call("DELETE", "/clients/admin", keys["school"]).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [("PATCH", "/clients/ghost"), ("POST", "/clients/ghost/key"), ("DELETE", "/clients/ghost")],
)
def test_unknown_clients_are_not_found(keys: dict[str, str], method: str, path: str) -> None:
    response = _call(method, path, keys["admin"], {"active": True} if method == "PATCH" else None)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
