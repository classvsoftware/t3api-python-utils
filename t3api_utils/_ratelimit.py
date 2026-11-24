"""A thread-safe token bucket shared by every request one client makes."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """Allows ``rate`` requests per second, with bursts of up to ``burst``.

    ``acquire()`` reserves a slot and sleeps until that slot's time, outside the
    lock, so waiting threads are spaced out evenly instead of all waking at once.
    A ``rate`` of ``None`` or ``0`` disables limiting.
    """

    def __init__(
        self,
        rate: float | None,
        *,
        burst: int = 1,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if rate is not None and rate < 0:
            raise ValueError("rate must be positive, or None to disable rate limiting")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        self.rate = rate or 0.0
        self.burst = burst
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._tokens = float(burst)
        self._last = clock()

    def acquire(self) -> float:
        """Wait for a slot. Returns how long it waited, in seconds."""
        if self.rate <= 0:
            return 0.0
        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._last)
            self._tokens = min(float(self.burst), self._tokens + elapsed * self.rate)
            self._last = now
            self._tokens -= 1.0
            wait = -self._tokens / self.rate if self._tokens < 0 else 0.0
        if wait > 0:
            # Looked up at call time, so a patched time.sleep (tests) applies.
            (self._sleep or time.sleep)(wait)
        return wait
