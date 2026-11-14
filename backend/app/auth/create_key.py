"""Admin command that creates a client key.

Usage: `uv run python -m app.auth.create_key --client acme --daily-limit 100`

Prints the key once, plus the JSON entry (with the hash) to add to `API_KEYS`. The key itself
is never stored: if it is lost, create a new one and replace the entry.
"""

import argparse
import sys

from app.auth.keys import generate_key, hash_key
from app.core.config import ApiKeyEntry, Settings, get_settings


def create_entry(
    client_id: str, settings: Settings, *, per_minute_limit: int, daily_limit: int
) -> tuple[str, ApiKeyEntry]:
    if not settings.api_key_pepper.get_secret_value():
        message = "API_KEY_PEPPER is empty: set it in the .env file before creating keys."
        raise ValueError(message)
    if any(entry.id == client_id for entry in settings.api_keys):
        message = f"The client '{client_id}' already exists in API_KEYS; replace its entry."
        raise ValueError(message)
    key = generate_key(client_id)
    entry = ApiKeyEntry(
        id=client_id,
        hash=hash_key(key, settings.api_key_pepper.get_secret_value()),
        per_minute_limit=per_minute_limit,
        daily_limit=daily_limit,
    )
    return key, entry


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an API key for a client.")
    parser.add_argument("--client", required=True, help="Client id: lowercase, digits and '-'")
    parser.add_argument("--per-minute-limit", type=int, default=10)
    parser.add_argument("--daily-limit", type=int, default=100)
    args = parser.parse_args(argv)

    current = settings or get_settings()
    try:
        key, entry = create_entry(
            args.client,
            current,
            per_minute_limit=args.per_minute_limit,
            daily_limit=args.daily_limit,
        )
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if not current.has_secure_pepper():
        sys.stderr.write(
            "warning: API_KEY_PEPPER is a placeholder or too short; use a long random secret "
            "outside development.\n"
        )
    sys.stdout.write(
        f"API key for '{entry.id}' (shown only once, give it to the client):\n{key}\n\n"
        "Add this entry to API_KEYS in the .env file:\n"
        f"{entry.model_dump_json()}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
