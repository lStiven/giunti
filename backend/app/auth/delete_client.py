"""Admin command that deletes a client or an administrator, its key and its usage history.

Usage:
    uv run python -m app.auth.delete_client colegio-san-jose

The admin panel deletes clients; administrators can only be deleted here. The key stops working
at once and the deletion cannot be undone.
"""

import argparse
import sys

from sqlalchemy.orm import Session

from app.auth.models import create_tables
from app.auth.store import ClientRepository
from app.core.config import Settings, get_settings
from app.core.database import make_engine


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete a client (or administrator) API key.")
    parser.add_argument("client_id", help="Id shown in the admin panel, e.g. 'colegio-san-jose'")
    args = parser.parse_args(argv)

    current = settings or get_settings()
    engine = make_engine(current.database_url)
    create_tables(engine)
    try:
        with Session(engine) as session:
            deleted = ClientRepository(session).delete(args.client_id)
    finally:
        engine.dispose()

    if not deleted:
        sys.stderr.write(f"error: the client '{args.client_id}' does not exist.\n")
        return 1
    sys.stdout.write(f"Client '{args.client_id}' deleted: its key no longer works.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
