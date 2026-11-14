"""In-memory per-client rate limiting (per minute and per day).

Counters are per process: with several instances each one keeps its own counts.
"""
