"""Admin command that creates a client key.

Usage: `uv run python -m app.auth.create_key --client acme --daily-limit 100`

Prints the key once, plus the JSON entry (with the hash) to append to `API_KEYS`.
"""
