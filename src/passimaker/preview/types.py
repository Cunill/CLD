"""Protocols of the preview (docs/CONTRACTES.md §10): the master clock and the sound output."""

from __future__ import annotations

from typing import Protocol

from passimaker.audio import AudioSource
from passimaker.common import RGBImage


class Clock(Protocol):
    """Master clock. The real one follows the audio device; tests use a simulated one."""

    def now(self) -> float:
        """Seconds of show time currently being heard."""
        ...


class AudioOutput(Protocol):
    def start(self, source: AudioSource, from_s: float) -> Clock:
        """Starts playing `source` from `from_s` (stopping what was playing) and returns its clock."""
        ...

    def stop(self) -> None: ...


class FrameSource(Protocol):
    """What the player needs from the compositor (passimaker.render.Compositor)."""

    def frame_at(self, t: float, width: int, height: int, *, sentinel: bool = False) -> RGBImage: ...
