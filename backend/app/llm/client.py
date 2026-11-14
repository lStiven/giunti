"""LiteLLM-based client.

`complete(messages, require_vision)` walks the configured fallback chain, skipping models that
lack vision when required, are open in the circuit breaker, or have too small a context. Logs the
model, attempts, tokens, cost and duration, never the content.
"""
