"""B13 · Which frame to draw next, and the internal clock."""

from __future__ import annotations

import pytest

from passimaker.preview import FrameScheduler, MonotonicClock
from passimaker.preview.params import COST_MAX_S


def test_aims_where_the_clock_will_be_when_the_frame_is_ready() -> None:
    scheduler = FrameScheduler(30, 300, cost_s=0.1)
    assert scheduler.next_frame(1.0) == 33  # (1.0 + 0.1) * 30


def test_never_draws_the_same_frame_twice_or_goes_back() -> None:
    scheduler = FrameScheduler(30, 300, cost_s=0.0)
    assert scheduler.next_frame(0.0) == 0
    scheduler.drawn(0, 0.0)
    assert scheduler.next_frame(0.01) is None
    assert scheduler.wait_s(0.01) == pytest.approx(1 / 30 - 0.01)
    assert scheduler.next_frame(1 / 30) == 1
    scheduler.drawn(5, 0.0)
    assert scheduler.next_frame(4 / 30) is None


def test_reset_draws_again_at_once() -> None:
    scheduler = FrameScheduler(30, 300, cost_s=0.0)
    scheduler.drawn(10, 0.0)
    scheduler.reset()
    assert scheduler.last_frame is None
    assert scheduler.next_frame(0.0) == 0
    assert scheduler.wait_s(0.0) == 0.0


def test_the_cost_estimate_follows_the_measured_times() -> None:
    scheduler = FrameScheduler(30, 300, cost_s=0.0)
    for frame in range(30):
        scheduler.drawn(frame, 0.08)
    assert scheduler.cost_s == pytest.approx(0.08, abs=0.001)
    scheduler.drawn(31, 10.0)
    assert scheduler.cost_s <= COST_MAX_S


def test_the_last_frame_is_the_end() -> None:
    scheduler = FrameScheduler(30, 60, cost_s=0.0)
    assert scheduler.next_frame(100.0) == 59
    scheduler.drawn(59, 0.0)
    assert scheduler.next_frame(100.0) is None
    assert FrameScheduler(30, 0).next_frame(0.0) is None


def test_monotonic_clock_starts_where_asked() -> None:
    ticks = iter([5.0, 5.0, 5.5, 7.0])
    clock = MonotonicClock(12.0, timer=lambda: next(ticks))
    assert clock.now() == 12.0
    assert clock.now() == 12.5
    assert clock.now() == 14.0
