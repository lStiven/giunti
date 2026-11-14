from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import create_tables
from app.core.database import IN_MEMORY_SQLITE, get_session, make_engine
from app.main import app


@pytest.fixture(autouse=True)
def database() -> Iterator[sessionmaker[Session]]:
    """A fresh in-memory database per test, so no test touches the real database file."""
    engine = make_engine(IN_MEMORY_SQLITE)
    create_tables(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    def session() -> Iterator[Session]:
        with sessions() as current:
            yield current

    app.dependency_overrides[get_session] = session
    yield sessions
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
