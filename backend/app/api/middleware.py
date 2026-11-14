"""Request middleware.

Assigns a request id (or reuses the `X-Request-ID` header), exposes it in
`app.core.logging.request_id_var` and in the response headers, and logs each request's duration.
"""
