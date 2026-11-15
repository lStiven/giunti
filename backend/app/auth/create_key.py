"""Admin command that creates a client or an administrator directly in the database.

Usage:
    uv run python -m app.auth.create_key --name "Administración" --admin
    uv run python -m app.auth.create_key --name "Colegio San José" --daily-limit 100
    uv run python -m app.auth.create_key --name "Administración" --admin --env-file .env.production

The first administrator must be created here; after that, clients are created from the admin
panel. Prints the key once and the invitation link that signs the person in with one click.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.auth.clients import ClientLimits, issue_client
from app.auth.models import create_tables
from app.auth.store import ClientRepository
from app.core.config import Settings, get_settings
from app.core.database import make_engine


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a client (or administrator) API key.")
    parser.add_argument("--name", required=True, help="Display name, e.g. 'Colegio San José'")
    parser.add_argument("--admin", action="store_true", help="Can use the admin panel")
    parser.add_argument("--per-minute-limit", type=int, default=10)
    parser.add_argument("--daily-limit", type=int, default=100)
    parser.add_argument(
        "--env-file", type=Path, help="Read the settings from this file instead of .env"
    )
    args = parser.parse_args(argv)

    current = settings or _settings(args.env_file)
    engine = make_engine(current.database_url)
    create_tables(engine)
    try:
        with Session(engine) as session:
            issued = issue_client(
                ClientRepository(session),
                current,
                name=args.name,
                limits=ClientLimits(per_minute=args.per_minute_limit, daily=args.daily_limit),
                is_admin=args.admin,
            )
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    finally:
        engine.dispose()

    if not current.has_secure_pepper():
        sys.stderr.write(
            "warning: API_KEY_PEPPER is a placeholder or too short; use a long random secret "
            "outside development.\n"
        )
    role = "Administrator" if args.admin else "Client"
    sys.stdout.write(
        f"{role} '{issued.client.name}' created (id: {issued.client.id}).\n\n"
        f"Invitation link (sign-in with one click):\n{issued.invite_url}\n\n"
        f"API key (shown only once):\n{issued.api_key}\n"
    )
    return 0


def _settings(env_file: Path | None) -> Settings:
    return Settings(_env_file=env_file) if env_file else get_settings()


if __name__ == "__main__":
    sys.exit(main())
