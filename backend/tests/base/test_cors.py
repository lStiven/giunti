from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

ORIGIN = "https://cuestionarios.example"


@pytest.fixture
def cors_app() -> Iterator[FastAPI]:
    get_settings.cache_clear()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "app.main.get_settings", lambda: Settings(cors_origins=[ORIGIN], log_level="WARNING")
        )
        yield create_app()
    get_settings.cache_clear()


def test_preflight_allows_the_api_key_header(cors_app: FastAPI) -> None:
    response = TestClient(cors_app).options(
        "/api/v1/models",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "x-api-key" in response.headers["Access-Control-Allow-Headers"].lower()


def test_error_responses_expose_run_and_limit_headers(cors_app: FastAPI) -> None:
    response = TestClient(cors_app).get("/api/v1/models", headers={"Origin": ORIGIN})

    assert response.status_code == 401
    exposed = response.headers["Access-Control-Expose-Headers"]
    assert "X-Extraction-Warnings" in exposed
    assert "Retry-After" in exposed


def test_unknown_origins_are_not_allowed(cors_app: FastAPI) -> None:
    response = TestClient(cors_app).get("/health", headers={"Origin": "https://evil.example"})

    assert "Access-Control-Allow-Origin" not in response.headers
