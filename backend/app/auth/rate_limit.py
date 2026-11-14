"""In-memory per-client rate limiting: a sliding one-minute window and a UTC calendar day.

Counters are per process: with several instances each one keeps its own counts. Checking and
recording happen without awaiting in between, so concurrent requests cannot both slip through.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

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


@dataclass(slots=True)
class _Usage:
    day: date
    day_count: int = 0
    recent: deque[float] = field(default_factory=deque)


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._usage: dict[str, _Usage] = {}

    def consume(self, client_id: str, quota: Quota) -> QuotaStatus:
        """Records one request, or raises RATE_LIMITED with the seconds to wait."""
        now = self._clock()
        today = datetime.fromtimestamp(now, UTC).date()
        usage = self._usage.setdefault(client_id, _Usage(day=today))
        if usage.day != today:
            usage.day, usage.day_count = today, 0
        while usage.recent and now - usage.recent[0] >= WINDOW_S:
            usage.recent.popleft()

        if usage.day_count >= quota.daily:
            message = f"Daily limit of {quota.daily} extractions reached. It resets at 00:00 UTC."
            raise AppError(
                ErrorCode.RATE_LIMITED,
                message,
                retry_after_s=_until_midnight(now),
                reason=ErrorReason.DAILY_LIMIT,
                details={"limit": quota.daily},
            )
        if len(usage.recent) >= quota.per_minute:
            wait = math.ceil(WINDOW_S - (now - usage.recent[0]))
            message = f"Limit of {quota.per_minute} extractions per minute reached."
            raise AppError(
                ErrorCode.RATE_LIMITED,
                message,
                retry_after_s=max(wait, 1),
                reason=ErrorReason.PER_MINUTE_LIMIT,
                details={"limit": quota.per_minute},
            )

        usage.recent.append(now)
        usage.day_count += 1
        return QuotaStatus(daily_limit=quota.daily, daily_remaining=quota.daily - usage.day_count)

    def used_today(self, client_id: str) -> int:
        """Extractions of the client today (UTC) counted by this process."""
        usage = self._usage.get(client_id)
        today = datetime.fromtimestamp(self._clock(), UTC).date()
        return usage.day_count if usage is not None and usage.day == today else 0


def _until_midnight(now: float) -> int:
    current = datetime.fromtimestamp(now, UTC)
    midnight = datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), UTC)
    return max(math.ceil((midnight - current).total_seconds()), 1)
