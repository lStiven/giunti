from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from app.auth.create_key import main as create_key_main
from app.auth.delete_client import main as delete_client_main
from app.auth.dependencies import AuthenticatedClient, get_rate_limiter, require_extraction_quota
from app.auth.keys import client_id_of, generate_key, hash_key, key_matches
from app.auth.rate_limit import DailyUsage, MemoryDailyUsage, Quota, RateLimiter
from app.auth.store import ClientRepository, NewClient, UsageRepository
from app.core.config import LLMCatalog, Settings, get_settings
from app.core.database import make_engine
from app.core.errors import AppError, ErrorCode
from app.main import app

PEPPER = "p" * 40
CATALOG = LLMCatalog.model_validate(
    {
        "default_model": "flash",
        "providers": {"gemini": {"label": "Gemini", "description": "d"}},
        "models": [{"id": "flash", "model": "gemini/flash"}],
    }
)
ACME_KEY = generate_key("acme")
OFF_KEY = generate_key("off")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "api_key_pepper": SecretStr(PEPPER),
        "llm_catalog": CATALOG,
        "gemini_api_key": SecretStr("g"),
        **overrides,
    }
    return Settings.model_validate(values)


def _default_settings() -> Settings:
    """Dependency override: FastAPI would read `_settings` keyword arguments as query params."""
    return _settings()


@pytest.fixture(autouse=True)
def _clients(database: sessionmaker[Session]) -> Iterator[None]:
    with database() as session:
        clients = ClientRepository(session)
        clients.create(_new_client("acme", ACME_KEY, daily_limit=5))
        clients.create(_new_client("off", OFF_KEY))
        clients.update("off", active=False)
    app.dependency_overrides[get_settings] = _default_settings
    yield
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_rate_limiter, None)


def _new_client(client_id: str, key: str, *, daily_limit: int = 100) -> NewClient:
    return NewClient(
        name=client_id.title(),
        key_hash=hash_key(key, PEPPER),
        per_minute_limit=10,
        daily_limit=daily_limit,
        client_id=client_id,
    )


def _headers(key: str | None) -> dict[str, str]:
    return {"X-API-Key": key} if key is not None else {}


@dataclass
class FakeClock:
    now: float

    def __call__(self) -> float:
        return self.now


def _at(text: str) -> FakeClock:
    return FakeClock(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp())


def _rate_limited(limiter: RateLimiter, quota: Quota, daily: DailyUsage) -> AppError:
    with pytest.raises(AppError) as error:
        limiter.consume("acme", quota, daily)
    assert error.value.code is ErrorCode.RATE_LIMITED
    return error.value


def test_generated_keys_embed_the_client_and_are_unique() -> None:
    key = generate_key("acme")

    assert key.startswith("gk_acme_")
    assert client_id_of(key) == "acme"
    assert generate_key("acme") != key


@pytest.mark.parametrize("key", ["", "acme", "gk_acme", "gk__secret", "xx_acme_secret", "gk_A_x"])
def test_malformed_keys_have_no_client(key: str) -> None:
    assert client_id_of(key) is None


def test_invalid_client_ids_are_rejected_when_generating() -> None:
    with pytest.raises(ValueError, match="Invalid client id"):
        generate_key("Acme Corp")


def test_key_hash_depends_on_the_pepper_and_verifies_only_the_right_key() -> None:
    digest = hash_key(ACME_KEY, PEPPER)

    assert key_matches(ACME_KEY, digest, PEPPER)
    assert not key_matches(OFF_KEY, digest, PEPPER)
    assert hash_key(ACME_KEY, "other pepper") != digest


def test_valid_key_is_accepted() -> None:
    assert TestClient(app).get("/api/v1/models", headers=_headers(ACME_KEY)).status_code == 200


def test_missing_key_is_unauthenticated() -> None:
    response = TestClient(app).get("/api/v1/models", headers=_headers(None))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "X-API-Key" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "key",
    [
        "not-a-key",
        generate_key("ghost"),
        ACME_KEY[:-1] + ("A" if ACME_KEY[-1] != "A" else "B"),
    ],
    ids=["malformed", "unknown client", "wrong secret"],
)
def test_bad_keys_get_the_same_error(key: str) -> None:
    response = TestClient(app).get("/api/v1/models", headers=_headers(key))

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "The API key is not valid."


def test_disabled_key_is_forbidden() -> None:
    response = TestClient(app).get("/api/v1/models", headers=_headers(OFF_KEY))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_listing_models_does_not_consume_quota() -> None:
    limiter = RateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter

    for _ in range(10):
        assert TestClient(app).get("/api/v1/models", headers=_headers(ACME_KEY)).status_code == 200


def test_extraction_without_key_is_rejected_before_reading_the_document() -> None:
    response = TestClient(app).post(
        "/api/v1/questionnaires", files={"file": ("t.pdf", b"%PDF-1.4")}
    )

    assert response.status_code == 401


def test_extraction_quota_is_consumed_reported_and_marks_the_client_as_used(
    database: sessionmaker[Session],
) -> None:
    client = AuthenticatedClient(id="acme", quota=Quota(per_minute=10, daily=5))
    response = Response()

    with database() as session:
        clients = ClientRepository(session)
        require_extraction_quota(response, client, RateLimiter(), clients, UsageRepository(session))
        last_used = clients.find("acme")

    assert response.headers["X-RateLimit-Limit-Day"] == "5"
    assert response.headers["X-RateLimit-Remaining-Day"] == "4"
    assert last_used is not None
    assert last_used.last_used_at is not None


def test_requests_over_the_per_minute_limit_wait_for_the_window() -> None:
    clock = _at("2026-11-14T10:00:00")
    limiter, daily = RateLimiter(clock), MemoryDailyUsage()
    quota = Quota(per_minute=2, daily=100)
    limiter.consume("acme", quota, daily)
    clock.now += 20
    limiter.consume("acme", quota, daily)

    error = _rate_limited(limiter, quota, daily)

    assert error.retry_after_s == 40
    clock.now += 40
    assert limiter.consume("acme", quota, daily).daily_remaining == 97


def test_daily_limit_resets_at_utc_midnight() -> None:
    clock = _at("2026-11-14T23:00:00")
    limiter, daily = RateLimiter(clock), MemoryDailyUsage()
    quota = Quota(per_minute=100, daily=1)
    limiter.consume("acme", quota, daily)

    error = _rate_limited(limiter, quota, daily)

    assert error.retry_after_s == 3600
    assert "Daily limit of 1" in error.message
    clock.now += 3600
    assert limiter.consume("acme", quota, daily).daily_remaining == 0


def test_clients_have_independent_limits() -> None:
    limiter, daily = RateLimiter(_at("2026-11-14T10:00:00")), MemoryDailyUsage()
    quota = Quota(per_minute=1, daily=1)
    limiter.consume("acme", quota, daily)

    assert limiter.consume("other", quota, daily).daily_remaining == 0


def test_daily_usage_survives_a_restart_because_it_lives_in_the_database(
    database: sessionmaker[Session],
) -> None:
    quota = Quota(per_minute=10, daily=2)
    with database() as session:
        RateLimiter(_at("2026-11-14T10:00:00")).consume("acme", quota, UsageRepository(session))

    with database() as session:
        restarted = RateLimiter(_at("2026-11-14T18:00:00"))
        status = restarted.consume("acme", quota, UsageRepository(session))
        error = _rate_limited(restarted, quota, UsageRepository(session))

    assert status.daily_remaining == 0
    assert error.reason == "daily_limit"


def test_stored_daily_usage_stops_at_the_limit_and_is_counted_per_day(
    database: sessionmaker[Session],
) -> None:
    monday, tuesday = date(2026, 11, 16), date(2026, 11, 17)
    with database() as session:
        usage = UsageRepository(session)
        counts = [usage.try_increment("acme", monday, 2) for _ in range(3)]
        usage.try_increment("acme", tuesday, 2)
        usage.try_increment("off", monday, 2)

        assert counts == [1, 2, None]
        assert usage.count("acme", monday) == 2
        assert usage.counts_on(monday) == {"acme": 2, "off": 1}
        assert usage.counts_on(tuesday) == {"acme": 1}


def test_a_request_rejected_by_the_daily_limit_does_not_use_a_minute_slot() -> None:
    limiter, daily = RateLimiter(_at("2026-11-14T10:00:00")), MemoryDailyUsage()
    tight, roomy = Quota(per_minute=1, daily=0), Quota(per_minute=1, daily=10)
    _rate_limited(limiter, tight, daily)

    assert limiter.consume("acme", roomy, daily).daily_remaining == 9


def test_rate_limited_response_has_retry_after_header(database: sessionmaker[Session]) -> None:
    limiter = RateLimiter(_at("2026-11-14T10:00:00"))
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    headers = {"X-API-Key": ACME_KEY}
    client = TestClient(app)
    with database() as session:
        for _ in range(5):
            UsageRepository(session).try_increment("acme", date(2026, 11, 14), 5)

    response = client.post(
        "/api/v1/questionnaires", files={"file": ("t.pdf", b"%PDF-1.4")}, headers=headers
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert int(response.headers["Retry-After"]) > 0


def test_create_key_command_stores_the_client_and_prints_its_key_and_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(
        database_url=f"sqlite:///{tmp_path / 'keys.db'}", public_app_url="https://app.example"
    )

    exit_code = create_key_main(["--name", "Colegio San José", "--daily-limit", "7"], settings)

    output = capsys.readouterr().out.splitlines()
    link, key = output[3], output[-1]
    assert exit_code == 0
    assert link == f"https://app.example/#clave={key}"
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        stored = ClientRepository(session).find("colegio-san-jose")
    engine.dispose()
    assert stored is not None
    assert stored.daily_limit == 7
    assert not stored.is_admin
    assert key_matches(key, stored.key_hash, PEPPER)


def test_delete_command_removes_any_client_including_administrators(tmp_path: Path) -> None:
    settings = _settings(database_url=f"sqlite:///{tmp_path / 'keys.db'}")
    create_key_main(["--name", "Old Admin", "--admin"], settings)

    deleted = delete_client_main(["old-admin"], settings)
    missing = delete_client_main(["old-admin"], settings)

    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        stored = ClientRepository(session).find("old-admin")
    engine.dispose()
    assert (deleted, missing) == (0, 1)
    assert stored is None


def test_admin_commands_read_the_settings_of_the_given_env_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Importing LiteLLM loads backend/.env into the environment, which would win over the file.
    for name in ("API_KEY_PEPPER", "DATABASE_URL", "PUBLIC_APP_URL"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "production.env"
    env_file.write_text(
        f"API_KEY_PEPPER={'q' * 40}\n"
        f"DATABASE_URL=sqlite:///{tmp_path / 'production.db'}\n"
        "PUBLIC_APP_URL=https://prod.example\n"
    )

    created = create_key_main(["--name", "Ops", "--admin", "--env-file", str(env_file)])
    output = capsys.readouterr().out
    deleted = delete_client_main(["ops", "--env-file", str(env_file)])

    assert (created, deleted) == (0, 0)
    assert "https://prod.example/admin#clave=gk_ops_" in output


def test_create_key_command_creates_administrators_with_an_admin_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(database_url=f"sqlite:///{tmp_path / 'keys.db'}")

    assert create_key_main(["--name", "Administración", "--admin"], settings) == 0

    output = capsys.readouterr().out
    assert output.startswith("Administrator 'Administración' created (id: administracion).")
    assert "/admin#clave=gk_administracion_" in output


def test_create_key_command_refuses_to_work_without_a_pepper(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(
        database_url=f"sqlite:///{tmp_path / 'keys.db'}", api_key_pepper=SecretStr("")
    )

    assert create_key_main(["--name", "Newco"], settings) == 1
    assert "API_KEY_PEPPER is empty" in capsys.readouterr().err


def test_production_requires_a_strong_pepper() -> None:
    with pytest.raises(ValueError, match="API_KEY_PEPPER"):
        Settings(app_env="production", api_key_pepper=SecretStr("change-me-to-a-long-random"))
