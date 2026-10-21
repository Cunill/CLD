"""Progress of an export: one fraction that never goes back, and the remaining time."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from passimaker.export.params import AUDIO_SHARE, ETA_MIN_FRAMES, FINISH_SHARE, PROGRESS_INTERVAL_S

type ExportProgress = Callable[[float, float | None], None]
"""Called as progress(fraction 0-1, seconds_remaining or None)."""


class ProgressTracker:
    """Turns the phases of the export (audio, frames, closing) into a single monotonic fraction.

    The remaining time is estimated from the frame rate measured since the first frames
    (warm-up excluded) plus the closing share; it is None only until that rate is known.
    """

    def __init__(
        self,
        callback: ExportProgress | None,
        total_frames: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._callback = callback
        self._total_frames = max(1, total_frames)
        self._clock = clock
        self._lock = threading.Lock()
        self._fraction = 0.0
        self._last_sent = float("-inf")
        self._eta_start: tuple[float, int] | None = None
        self._remaining: float | None = None

    @property
    def fraction(self) -> float:
        return self._fraction

    def start(self) -> None:
        self._report(0.0, force=True)

    def audio(self, done: int, total: int) -> None:
        self._report(AUDIO_SHARE * (done / total if total > 0 else 1.0))

    def frames(self, written: int) -> None:
        now = self._clock()
        if written >= ETA_MIN_FRAMES and self._eta_start is None:
            self._eta_start = (now, written)
        if self._eta_start is not None and written > self._eta_start[1]:
            started, first = self._eta_start
            per_frame = (now - started) / (written - first)
            left = self._total_frames - written
            self._remaining = per_frame * left * (1.0 + FINISH_SHARE / (1.0 - AUDIO_SHARE - FINISH_SHARE))
        share = 1.0 - AUDIO_SHARE - FINISH_SHARE
        self._report(AUDIO_SHARE + share * min(1.0, written / self._total_frames))

    def finished(self) -> None:
        self._remaining = 0.0
        self._report(1.0, force=True)

    def _report(self, fraction: float, *, force: bool = False) -> None:
        with self._lock:
            fraction = max(self._fraction, min(1.0, fraction))
            self._fraction = fraction
            now = self._clock()
            if not force and now - self._last_sent < PROGRESS_INTERVAL_S:
                return
            self._last_sent = now
            remaining = self._remaining
        if self._callback is not None:
            self._callback(fraction, None if remaining is None else max(0.0, remaining))
