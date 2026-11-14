"""Per-model circuit breaker: stops calling a model that keeps failing, for a while.

After `failure_threshold` consecutive failures the model is skipped for `cooldown_s`. After the
cooldown one call is let through; another failure opens the circuit again, a success closes it.
Quota and configuration failures pause the model immediately for a longer time.
State lives in memory, so it is per instance.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_S = 60.0


@dataclass
class CircuitBreaker:
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    cooldown_s: float = DEFAULT_COOLDOWN_S
    clock: Callable[[], float] = time.monotonic
    _consecutive_failures: int = field(default=0, init=False)
    _open_until: float = field(default=0.0, init=False)

    def is_available(self) -> bool:
        return self.clock() >= self._open_until

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self.pause(self.cooldown_s)
            # Half-open: a single failure after the cooldown reopens the circuit.
            self._consecutive_failures = self.failure_threshold - 1

    def pause(self, seconds: float) -> None:
        self._open_until = max(self._open_until, self.clock() + seconds)


@dataclass
class BreakerRegistry:
    clock: Callable[[], float] = time.monotonic
    _breakers: dict[str, CircuitBreaker] = field(default_factory=dict, init=False)

    def get(self, model: str) -> CircuitBreaker:
        if model not in self._breakers:
            self._breakers[model] = CircuitBreaker(clock=self.clock)
        return self._breakers[model]
