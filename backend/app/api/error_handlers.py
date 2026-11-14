"""Maps application errors to HTTP responses shaped as
`{"error": {"code": ..., "message": ..., "request_id": ...}}`.

401 unauthenticated, 403 forbidden, 413 file too large, 415 unsupported format,
422 invalid/empty/protected file or no text/items, 429 rate limited (with `Retry-After`),
502 LLM unavailable or invalid response, 500 internal error.
"""
