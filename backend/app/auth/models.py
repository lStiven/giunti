"""Database tables: the clients that can use the API (administrators included) and their usage."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    String,
    false,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, create_schema


class ClientRow(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    per_minute_limit: Mapped[int] = mapped_column(Integer)
    daily_limit: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    key_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allow_precise: Mapped[bool] = mapped_column(Boolean, server_default=false())
    """Can use the precise reasoning mode. New clients get what the administrator chooses (fast
    only by default). When the column was added, existing clients got fast only and existing
    administrators kept the precise mode."""


class DailyUsageRow(Base):
    """Extractions of a client on one UTC day. A separate table so that adding it needs no
    migration of `clients`: missing tables are created at startup."""

    __tablename__ = "daily_usage"

    client_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


# Columns added after the first release: definition (with the value existing rows get) and
# the statements that adjust existing rows. There are no migrations: each column is added at
# startup when missing, so the statements run once.
_ADDED_COLUMNS = {
    ("clients", "allow_precise"): (
        "BOOLEAN NOT NULL DEFAULT FALSE",
        ("UPDATE clients SET allow_precise = TRUE WHERE is_admin",),
    ),
}


def create_tables(engine: Engine) -> None:
    """Creates the missing tables and columns (importing this module registers them)."""
    create_schema(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for (table, column), (definition, adjustments) in _ADDED_COLUMNS.items():
            existing = {info["name"] for info in inspector.get_columns(table)}
            if column not in existing:
                # Fixed identifiers from _ADDED_COLUMNS, never user input.
                statement = f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                connection.execute(text(statement))
                for adjustment in adjustments:
                    connection.execute(text(adjustment))
