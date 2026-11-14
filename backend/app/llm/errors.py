"""Provider error classification built on LiteLLM exceptions.

TRANSIENT (429 per minute, 5xx, timeout): retry with backoff, then next model.
QUOTA_EXHAUSTED: no retry; the model is skipped until its quota resets.
CONFIGURATION (invalid key, unknown model): no retry; logged as an error; next model.
REFUSED (safety block): next model.
TRUNCATED (output limit reached): next model.
CONTEXT_EXCEEDED: skip models whose context window is too small.
"""
