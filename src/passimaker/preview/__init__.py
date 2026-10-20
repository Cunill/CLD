"""M10 · Real-time preview player (block B13). Qt is allowed here."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, Signal

from passimaker.audio import AudioSource
from passimaker.render import Compositor
from passimaker.timeline import Timeline

PREVIEW_MAX_SIZE = (960, 540)


class Clock(Protocol):
    """Master clock. The real one follows the audio device; tests use a simulated one."""

    def now(self) -> float:
        """Seconds of show time currently being heard."""
        ...


class AudioOutput(Protocol):
    def start(self, source: AudioSource, from_s: float) -> Clock: ...

    def stop(self) -> None: ...


class Player(QObject):
    """Contract:
    - play(), pause(), seek(t), seek_photo(index)
    - frame_ready(image: QImage, t: float) emitted from the GUI thread
    - state_changed(playing: bool, t: float, photo_index: int)
    """

    frame_ready = Signal(object, float)
    state_changed = Signal(bool, float, int)

    def __init__(
        self,
        compositor: Compositor,
        timeline: Timeline,
        audio: AudioSource | None,
        output: AudioOutput | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        raise NotImplementedError("B13")

    def play(self) -> None:
        raise NotImplementedError("B13")

    def pause(self) -> None:
        raise NotImplementedError("B13")

    def seek(self, t: float) -> None:
        raise NotImplementedError("B13")

    def seek_photo(self, index: int) -> None:
        raise NotImplementedError("B13")

    def refresh(self) -> None:
        """Redraws the current frame (after an edit while paused)."""
        raise NotImplementedError("B13")
