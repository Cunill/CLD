"""Which frame to draw next while playing: aim where the clock will be when the frame is ready.

A frame takes some time to draw. If the player drew the frame of the instant it reads the clock,
the frame would always reach the screen late by that time. Instead it aims at `now + cost`, the
cost being a running average of the last drawing times: the frame is ready just when its instant
is heard. Frames in between are skipped, so a slow computer shows fewer frames but never falls
behind the sound (§1.8).
"""

from __future__ import annotations

from passimaker.preview.params import COST_INITIAL_S, COST_MAX_S, COST_SMOOTHING
from passimaker.timeline import frame_to_time, time_to_frame


class FrameScheduler:
    """Pure decisions on frame indices; the render thread does the waiting and the drawing."""

    def __init__(self, fps: int, total_frames: int, cost_s: float = COST_INITIAL_S) -> None:
        self.fps = fps
        self.total_frames = total_frames
        self._cost = min(COST_MAX_S, max(0.0, cost_s))
        self._last: int | None = None

    @property
    def cost_s(self) -> float:
        """Current estimate of the time it takes to draw a frame."""
        return self._cost

    @property
    def last_frame(self) -> int | None:
        return self._last

    def reset(self) -> None:
        """Forgets the last frame drawn (after a seek): the next one is drawn straight away."""
        self._last = None

    def next_frame(self, now: float) -> int | None:
        """The frame to draw now, or None if the next one is not due yet (or the show is over)."""
        if self.total_frames <= 0:
            return None
        frame = min(self.total_frames - 1, max(0, time_to_frame(now + self._cost, self.fps)))
        if self._last is not None and frame <= self._last:
            return None
        return frame

    def wait_s(self, now: float) -> float:
        """How long to wait before the next frame is due (0 if it is due already)."""
        if self._last is None:
            return 0.0
        due = frame_to_time(self._last + 1, self.fps) - self._cost
        return max(0.0, due - now)

    def drawn(self, frame: int, cost_s: float) -> None:
        """Records a frame drawn and how long it took (in clock seconds)."""
        self._last = frame
        measured = min(COST_MAX_S, max(0.0, cost_s))
        self._cost += COST_SMOOTHING * (measured - self._cost)
