"""Simulated clock for preview tests: time only moves when the test says so."""

from __future__ import annotations


class SimulatedClock:
    """Implements passimaker.preview.Clock."""

    def __init__(self, start_s: float = 0.0) -> None:
        self._now = start_s

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("el rellotge no pot anar enrere")
        self._now += seconds

    def set(self, t_s: float) -> None:
        self._now = t_s
