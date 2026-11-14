"""`require_client` FastAPI dependency.

Reads `X-API-Key`, resolves the client from the key prefix, verifies the HMAC, checks that the
client is active and within its limits, and returns the authenticated client. Unknown and wrong
keys produce the same error so client ids cannot be enumerated.
"""
