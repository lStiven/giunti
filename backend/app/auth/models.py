"""Database tables: the clients that can use the API (administrators included) and their usage."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Engine, ForeignKey, Integer, String
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


class DailyUsageRow(Base):
    """Extractions of a client on one UTC day. A separate table so that adding it needs no
    migration of `clients`: missing tables are created at startup."""

    __tablename__ = "daily_usage"

    client_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


def create_tables(engine: Engine) -> None:
    """Creates the missing tables (importing this module registers them)."""
    create_schema(engine)
