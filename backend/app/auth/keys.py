"""API key generation and hashing.

Keys look like `gk_<client>_<secret>` with a 32-byte random secret. They are stored as
HMAC-SHA256 digests keyed with `API_KEY_PEPPER` and compared with `hmac.compare_digest`.
A slow password hash is unnecessary because keys are high-entropy random values.
"""
