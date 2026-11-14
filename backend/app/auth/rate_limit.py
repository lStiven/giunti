"""Per-client rate limiting: a sliding one-minute window and a UTC calendar day.

The one-minute window lives in memory: losing it on a restart frees at most a minute. Daily
counts go through `DailyUsage`, stored in the database in production, so they survive restarts
and instances that scale to zero. The daily increment is atomic, so concurrent requests cannot
both take the last unit.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from app.core.errors import AppError, ErrorCode, ErrorReason

WINDOW_S = 60.0


@dataclass(frozen=True, slots=True)
class Quota:
    per_minute: int
    daily: int


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    daily_limit: int
    daily_remaining: int


class DailyUsage(Protocol):
    def count(self, client_id: str, day: date) -> int:
        """Units the client used on that day."""
        ...

    def try_increment(self, client_id: str, day: date, limit: int) -> int | None:
        """Records one unit and returns the new count, or None when the limit was reached."""
        ...


class MemoryDailyUsage:
    """`DailyUsage` kept in this process only: for tests and tools without a database."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, date], int] = {}
        self._lock = threading.Lock()

    def count(self, client_id: str, day: date) -> int:
        return self._counts.get((client_id, day), 0)

    def try_increment(self, client_id: str, day: date, limit: int) -> int | None:
        with self._lock:
            current = self._counts.get((client_id, day), 0)
            if current >= limit:
                return None
            self._counts[client_id, day] = current + 1
            return current + 1


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._recent: dict[str, deque[float]] = {}
        # Quota dependencies are sync, so FastAPI runs them in worker threads.
        self._lock = threading.Lock()

    def today(self) -> date:
        return datetime.fromtimestamp(self._clock(), UTC).date()

    def consume(self, client_id: str, quota: Quota, daily: DailyUsage) -> QuotaStatus:
        """Records one request, or raises RATE_LIMITED with the seconds to wait."""
        now = self._clock()
        today = datetime.fromtimestamp(now, UTC).date()
        if daily.count(client_id, today) >= quota.daily:
            raise _daily_limit_error(quota, now)

        with self._lock:
            recent = self._recent.setdefault(client_id, deque())
            while recent and now - recent[0] >= WINDOW_S:
                recent.popleft()
            if len(recent) >= quota.per_minute:
                wait = math.ceil(WINDOW_S - (now - recent[0]))
                message = f"Limit of {quota.per_minute} extractions per minute reached."
                raise AppError(
                    ErrorCode.RATE_LIMITED,
                    message,
                    retry_after_s=max(wait, 1),
                    reason=ErrorReason.PER_MINUTE_LIMIT,
                    details={"limit": quota.per_minute},
                )
            recent.append(now)

        used = daily.try_increment(client_id, today, quota.daily)
        if used is None:
            # Another request took the last unit of the day: give back the minute slot.
            with self._lock:
                self._recent[client_id].remove(now)
            raise _daily_limit_error(quota, now)
        return QuotaStatus(daily_limit=quota.daily, daily_remaining=quota.daily - used)


def _daily_limit_error(quota: Quota, now: float) -> AppError:
    message = f"Daily limit of {quota.daily} extractions reached. It resets at 00:00 UTC."
    return AppError(
        ErrorCode.RATE_LIMITED,
        message,
        retry_after_s=_until_midnight(now),
        reason=ErrorReason.DAILY_LIMIT,
        details={"limit": quota.daily},
    )


def _until_midnight(now: float) -> int:
    current = datetime.fromtimestamp(now, UTC)
    midnight = datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), UTC)
    return max(math.ceil((midnight - current).total_seconds()), 1)
