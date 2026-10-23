"""Player: the Qt face of the playback loop (docs/CONTRACTES.md §10).

The loop runs on its own thread (passimaker.preview.loop). Each frame is turned into a QImage on
that thread, crosses to the interface thread through a queued signal and is emitted there as
`frame_ready` only if no seek or new scene has made it stale in the meantime.
"""

from __future__ import annotations

import contextlib
import threading

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from passimaker.audio import AudioSource
from passimaker.common import RGBImage
from passimaker.preview.clock import ClockFactory, MonotonicClock
from passimaker.preview.loop import Delivery, PlaybackLoop, PlayState, Scene, photo_index_at, photo_start
from passimaker.preview.params import PREVIEW_MAX_SIZE, THREAD_JOIN_TIMEOUT_S
from passimaker.preview.sound import SoundDeviceOutput
from passimaker.preview.types import AudioOutput, FrameSource
from passimaker.timeline import Timeline


def to_qimage(image: RGBImage) -> QImage:
    """An independent copy of an RGB array as a QImage (safe on any thread, unlike QPixmap)."""
    data = np.ascontiguousarray(image)
    height, width = data.shape[:2]
    raw = data.tobytes()  # kept in a name: QImage does not own the buffer until copy()
    return QImage(raw, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


class Player(QObject):
    """Contract:
    - play(), pause(), seek(t), seek_photo(index), refresh()
    - frame_ready(image: QImage, t: float) emitted from the GUI thread
    - state_changed(playing: bool, t: float, photo_index: int)

    Also (B13): set_scene() after an edit, set_size() for the frame size, close().
    With music and `output=None` the default sound device is used; without music (or if the
    device cannot be opened) an internal clock keeps the time.
    """

    frame_ready = Signal(object, float)
    state_changed = Signal(bool, float, int)
    _delivered = Signal(int, object, float)
    _notified = Signal(bool, float, int)

    def __init__(
        self,
        compositor: FrameSource,
        timeline: Timeline,
        audio: AudioSource | None,
        output: AudioOutput | None = None,
        parent: QObject | None = None,
        *,
        clock_factory: ClockFactory = MonotonicClock,
        size: tuple[int, int] = PREVIEW_MAX_SIZE,
    ) -> None:
        super().__init__(parent)
        self._timeline = timeline
        self._last_t = 0.0
        self._closed = False
        self._delivered.connect(self._on_delivered)
        self._notified.connect(self.state_changed)
        self._own_output: SoundDeviceOutput | None = None
        """The default sound output, when the player made it: close() closes its stream."""
        if output is None:
            output = self._own_output = SoundDeviceOutput()
        self._loop = PlaybackLoop(
            Scene(compositor, timeline, audio),
            output,
            self._deliver,
            self._notify,
            clock_factory=clock_factory,
            size=size,
        )
        self._thread = threading.Thread(
            target=self._loop.run, name="passimaker-previsualitzacio", daemon=True
        )
        self._thread.start()

    # --- Contract --------------------------------------------------------------------------------

    def play(self) -> None:
        self._loop.play()

    def pause(self) -> None:
        self._loop.pause()

    def seek(self, t: float) -> None:
        self._last_t = min(max(0.0, t), self._timeline.total_duration_s)
        self._loop.seek(t)

    def seek_photo(self, index: int) -> None:
        self._last_t = photo_start(self._timeline, index)
        self._loop.seek_photo(index)

    def refresh(self) -> None:
        """Redraws the current frame (after an edit while paused)."""
        self._loop.refresh()

    # --- Extensions (B13) ------------------------------------------------------------------------

    def set_scene(
        self, compositor: FrameSource, timeline: Timeline, audio: AudioSource | None, at: float | None = None
    ) -> None:
        """A new version of the project: same position (or `at`); in pause, the frame is drawn again.

        If `audio` is a different object the sound restarts at the current position; if it is the
        same, playing goes on without a cut.
        """
        self._timeline = timeline
        if at is not None:
            self._last_t = min(max(0.0, at), timeline.total_duration_s)
        self._loop.set_scene(Scene(compositor, timeline, audio), at)

    def set_size(self, width: int, height: int) -> None:
        self._loop.set_size(width, height)

    def toggle(self) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()

    @property
    def playing(self) -> bool:
        return self._loop.playing

    @property
    def position(self) -> float:
        """Show time of the last frame shown, or where a seek is going (frames before it are dropped)."""
        return self._last_t

    @property
    def photo_index(self) -> int:
        return photo_index_at(self._timeline, self._last_t)

    @property
    def timeline(self) -> Timeline:
        return self._timeline

    def wait_idle(self, timeout_s: float = 10.0) -> bool:
        """Waits until the render thread is paused with nothing to do (tests)."""
        return self._loop.wait_idle(timeout_s)

    def close(self) -> None:
        """Stops the sound and the render thread (waits for the frame being drawn)."""
        if self._closed:
            return
        self._closed = True
        self._loop.close()
        self._thread.join(THREAD_JOIN_TIMEOUT_S)
        if self._own_output is not None:
            self._own_output.close()

    # --- Threads ---------------------------------------------------------------------------------

    def _deliver(self, delivery: Delivery) -> None:
        """Render thread: the QImage is built here, the signal is queued to the GUI thread."""
        if delivery.generation != self._loop.generation:
            return
        with contextlib.suppress(RuntimeError):  # the player was deleted while drawing
            self._delivered.emit(delivery.generation, to_qimage(delivery.image), delivery.t)

    def _notify(self, state: PlayState) -> None:
        with contextlib.suppress(RuntimeError):
            self._notified.emit(state.playing, state.t, state.photo_index)

    def _on_delivered(self, generation: int, image: object, t: float) -> None:
        if generation != self._loop.generation or self._closed:
            return
        self._last_t = t
        self.frame_ready.emit(image, t)
