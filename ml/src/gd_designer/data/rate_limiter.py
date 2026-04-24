import asyncio
import time


class TokenBucket:
    """Async token bucket. §4.1 of DATA_COLLECTION.md — 1 req/s average, small burst allowance.

    acquire() blocks the caller until a token is available. Safe under concurrency,
    but combine with Semaphore(1) in the fetch loop to enforce §4.2 (one in-flight).
    """

    def __init__(self, rate_per_sec: float, capacity: int = 3) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._rate = rate_per_sec
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now

            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._last = time.monotonic()
            else:
                self._tokens -= 1.0


class FailureStreak:
    """Tracks consecutive failures. §4.3 — after 3 in a row, sleep 15 min."""

    def __init__(self, threshold: int = 3, cooldown_sec: float = 900.0) -> None:
        self._threshold = threshold
        self._cooldown = cooldown_sec
        self._count = 0

    def success(self) -> None:
        self._count = 0

    async def failure(self) -> None:
        self._count += 1
        if self._count >= self._threshold:
            await asyncio.sleep(self._cooldown)
            self._count = 0
