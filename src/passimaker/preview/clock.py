"""The internal clock: show time when there is no music (or no sound device) (§1.8)."""

from __future__ import annotations

import time
from collections.abc import Callable

from passimaker.preview.types import Clock

type ClockFactory = Callable[[float], Clock]
"""Builds a clock that starts at the given show time (the internal one, or a simulated one)."""


class MonotonicClock:
    """Implements Clock with the computer's monotonic clock, starting at `from_s`."""

    def __init__(self, from_s: float = 0.0, timer: Callable[[], float] = time.perf_counter) -> None:
        self._from = from_s
        self._timer = timer
        self._started = timer()

    def now(self) -> float:
        return self._from + (self._timer() - self._started)
