from dataclasses import dataclass

from app.llm.circuit_breaker import BreakerRegistry, CircuitBreaker


@dataclass
class FakeClock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def test_breaker_stays_closed_below_the_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, clock=FakeClock())

    breaker.record_failure()
    breaker.record_failure()

    assert breaker.is_available()


def test_breaker_opens_after_consecutive_failures_until_the_cooldown_ends() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_s=60, clock=clock)

    for _ in range(3):
        breaker.record_failure()

    assert not breaker.is_available()
    clock.now += 60
    assert breaker.is_available()


def test_a_success_resets_the_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=2, clock=FakeClock())

    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()

    assert breaker.is_available()


def test_one_failure_after_the_cooldown_reopens_the_breaker() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_s=60, clock=clock)
    for _ in range(3):
        breaker.record_failure()
    clock.now += 60

    breaker.record_failure()

    assert not breaker.is_available()


def test_pause_keeps_the_longest_pause() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(clock=clock)

    breaker.pause(600)
    breaker.pause(10)
    clock.now += 599

    assert not breaker.is_available()


def test_registry_keeps_one_breaker_per_model() -> None:
    registry = BreakerRegistry(clock=FakeClock())

    registry.get("a").pause(100)

    assert not registry.get("a").is_available()
    assert registry.get("b").is_available()
