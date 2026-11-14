"""Database access shared by the app: one engine per process and a session per request.

SQLite (a local file) by default, any SQLAlchemy URL in production. Tables are created at
startup; with a single small table there are no migrations yet.
"""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from app.core.config import get_settings

SQLITE_PREFIX = "sqlite:///"
IN_MEMORY_SQLITE = "sqlite://"


class Base(DeclarativeBase): ...


def make_engine(url: str) -> Engine:
    if url == IN_MEMORY_SQLITE:
        engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    elif url.startswith(SQLITE_PREFIX):
        Path(url.removeprefix(SQLITE_PREFIX)).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(url, pool_pre_ping=True)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(connection: DBAPIConnection, _: ConnectionPoolEntry) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session that is closed after the request."""
    with _session_factory()() as session:
        yield session
