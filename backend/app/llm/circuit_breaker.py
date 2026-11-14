"""Per-model circuit breaker: after N consecutive failures a model is skipped for a cool-down
period (or until its quota resets). State is kept in memory.
"""
