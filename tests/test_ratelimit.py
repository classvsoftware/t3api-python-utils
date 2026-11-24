"""_ratelimit.py: the token bucket."""

from __future__ import annotations

import threading
import time

import pytest

from t3api_utils._ratelimit import TokenBucket


class FakeClock:
    """Simulated time: sleeping advances the clock instead of waiting."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_twenty_acquires_at_rate_ten_take_one_point_nine_seconds() -> None:
    clock = FakeClock()
    bucket = TokenBucket(10, clock=clock, sleep=clock.sleep)
    start = clock.now
    times = []
    for _ in range(20):
        bucket.acquire()
        times.append(clock.now)
    assert clock.now - start == pytest.approx(1.9)
    # Evenly spaced, one every 100 ms: no burst at the start.
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps == pytest.approx([0.1] * 19)
    assert times[1] - times[0] == pytest.approx(0.1)


def test_first_acquire_does_not_wait_and_returns_wait() -> None:
    clock = FakeClock()
    bucket = TokenBucket(4, clock=clock, sleep=clock.sleep)
    assert bucket.acquire() == 0.0
    assert bucket.acquire() == pytest.approx(0.25)
    assert clock.sleeps == pytest.approx([0.25])


def test_idle_time_refills_but_never_beyond_burst() -> None:
    clock = FakeClock()
    bucket = TokenBucket(10, burst=3, clock=clock, sleep=clock.sleep)
    clock.now += 100.0  # a long idle period
    waits = [bucket.acquire() for _ in range(4)]
    assert waits[:3] == [0.0, 0.0, 0.0]
    assert waits[3] == pytest.approx(0.1)


def test_burst_allows_that_many_without_waiting() -> None:
    clock = FakeClock()
    bucket = TokenBucket(5, burst=5, clock=clock, sleep=clock.sleep)
    assert [bucket.acquire() for _ in range(5)] == [0.0] * 5
    assert clock.sleeps == []
    assert bucket.acquire() == pytest.approx(0.2)


def test_clock_going_backwards_is_treated_as_no_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(10, clock=clock, sleep=clock.sleep)
    bucket.acquire()
    clock.now -= 50.0
    assert bucket.acquire() == pytest.approx(0.1)


@pytest.mark.parametrize("rate", [None, 0, 0.0])
def test_none_or_zero_disables(rate: float | None) -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate, clock=clock, sleep=clock.sleep)
    assert bucket.rate == 0.0
    assert [bucket.acquire() for _ in range(50)] == [0.0] * 50
    assert clock.sleeps == []


def test_negative_rate_raises() -> None:
    with pytest.raises(ValueError, match="rate"):
        TokenBucket(-1)


def test_burst_below_one_raises() -> None:
    with pytest.raises(ValueError, match="burst"):
        TokenBucket(10, burst=0)


def test_threads_get_distinct_evenly_spaced_slots() -> None:
    # Time never moves, so every acquire must reserve its own later slot.
    lock = threading.Lock()
    waits: list[float] = []

    def record(seconds: float) -> None:
        with lock:
            waits.append(seconds)

    bucket = TokenBucket(10, clock=lambda: 0.0, sleep=record)
    barrier = threading.Barrier(16)

    def worker() -> None:
        barrier.wait()
        bucket.acquire()

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # One thread got the free token; the other 15 slept 0.1, 0.2, ... 1.5.
    assert sorted(waits) == pytest.approx([0.1 * i for i in range(1, 16)])


def test_default_sleep_is_time_sleep_looked_up_at_call_time(sleeps: list[float]) -> None:
    # conftest replaces time.sleep with a recorder after this module was
    # imported; the bucket must still use it.
    bucket = TokenBucket(10, clock=lambda: 0.0)
    bucket.acquire()
    bucket.acquire()
    assert sleeps == pytest.approx([0.1])


def test_default_clock_is_monotonic() -> None:
    bucket = TokenBucket(1000)
    before = time.monotonic()
    bucket.acquire()
    assert bucket._last >= before
