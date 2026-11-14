"""Database table of the clients that can use the API (administrators included)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Engine, Integer, String
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


def create_tables(engine: Engine) -> None:
    """Creates the missing tables (importing this module registers them)."""
    create_schema(engine)
