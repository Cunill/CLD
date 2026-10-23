"""Simulated sound device and frame sources for the preview tests (no sound card, no real time)."""

from __future__ import annotations

import threading
from collections.abc import Sequence

import numpy as np

from passimaker.audio import AudioSource
from passimaker.common import RGBImage
from passimaker.preview import Clock, FrameSource
from tests.fakes.clock import SimulatedClock


class FakeAudioOutput:
    """Implements AudioOutput: one SimulatedClock that jumps to `from_s` at every start.

    Records every start and stop, so the tests can check the sound is not cut while playing.
    """

    def __init__(self, clock: SimulatedClock | None = None, fail: bool = False) -> None:
        self.clock = clock if clock is not None else SimulatedClock()
        self.fail = fail
        self.starts: list[float] = []
        self.stops = 0
        self.playing = False
        self.source: AudioSource | None = None

    def start(self, source: AudioSource, from_s: float) -> Clock:
        if self.fail:
            raise OSError("cap dispositiu de so")
        self.starts.append(from_s)
        self.clock.set(from_s)
        self.playing = True
        self.source = source
        return self.clock

    def stop(self) -> None:
        self.stops += 1
        self.playing = False


class SimulatedClockFactory:
    """ClockFactory for the internal clock in tests: the same SimulatedClock, moved to `from_s`."""

    def __init__(self, clock: SimulatedClock | None = None) -> None:
        self.clock = clock if clock is not None else SimulatedClock()
        self.starts: list[float] = []

    def __call__(self, from_s: float) -> Clock:
        self.starts.append(from_s)
        self.clock.set(from_s)
        return self.clock


class SlowFrames:
    """A FrameSource that takes time on the simulated clock: `costs_s` in turn, for every frame.

    Wraps a real one (or draws a grey frame) and records the instants asked for.
    """

    def __init__(
        self,
        clock: SimulatedClock,
        costs_s: Sequence[float] = (0.005,),
        inner: FrameSource | None = None,
    ) -> None:
        self.clock = clock
        self.costs_s = list(costs_s)
        self.inner = inner
        self.times: list[float] = []
        self.sizes: list[tuple[int, int]] = []
        self._lock = threading.Lock()

    def frame_at(self, t: float, width: int, height: int, *, sentinel: bool = False) -> RGBImage:
        with self._lock:
            cost = self.costs_s[len(self.times) % len(self.costs_s)]
            self.times.append(t)
            self.sizes.append((width, height))
        self.clock.advance(cost)
        if self.inner is not None:
            return self.inner.frame_at(t, width, height, sentinel=sentinel)
        return np.full((height, width, 3), 128, dtype=np.uint8)
