"""The trim of a song (§1.7): its waveform, with two handles for "Comença a" and "Acaba a".

``TrimBar`` only draws and reports: while a handle is dragged it emits ``trim_moving`` (the
number boxes follow it), and when it is released ``trim_changed`` (the song panel turns it into a
single command, so a drag is a single step of undo). The start can never pass the end.

``WaveformLoader`` reads the peaks of a file with FFmpeg in a worker thread (rule 6) and keeps
them, so selecting the same song again draws it at once.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from passimaker.common import PassiMakerError
from passimaker.ffmpeg import waveform
from passimaker.model import defaults

_log = logging.getLogger(__name__)

WAVEFORM_POINTS = 600
"""Peaks per song: one every 2 px on a wide panel."""
TRIM_STEP_S = defaults.SONG_TRIM_STEP_S
"""The trim boxes go in tenths of a second; the start stays at least this far from the end."""
HANDLE_GRAB_PX = 10
"""A press closer than this to a handle takes that handle; elsewhere, the closest one jumps there."""
HANDLE_WIDTH = 4
BAR_HEIGHT = 72

WAVE_COLOUR = QColor(70, 130, 200)
HANDLE_COLOUR = QColor(230, 140, 20)
OUTSIDE_SHADE = QColor(0, 0, 0, 120)

type Peaks = NDArray[np.float32]
type WaveformReader = Callable[[Path, int], Peaks]


class TrimBar(QWidget):
    """Waveform of the whole file; the part outside [start, end] is shaded."""

    trim_moving = Signal(float, float)
    """A handle is being dragged: (start, end) in seconds of the file."""
    trim_changed = Signal(float, float)
    """A handle was released at a new place."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._duration = 0.0
        self._start = 0.0
        self._end = 0.0
        self._peaks: Peaks | None = None
        self._message = ""
        self._dragging: str | None = None
        self._before_drag = (0.0, 0.0)
        self.setMinimumHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(400, BAR_HEIGHT)

    # --- State -----------------------------------------------------------------------------------

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def start(self) -> float:
        return self._start

    @property
    def end(self) -> float:
        return self._end

    @property
    def dragging(self) -> bool:
        return self._dragging is not None

    def set_song(self, duration_s: float, start: float, end: float) -> None:
        self._duration = max(0.0, duration_s)
        self.set_trim(start, end)

    def set_trim(self, start: float, end: float) -> None:
        """Shows this trim (from the project or the number boxes); a drag in progress wins."""
        if self._dragging is None:
            self._start, self._end = limit_trim(start, end, self._duration)
            self.update()

    def set_peaks(self, peaks: Peaks | None, message: str = "") -> None:
        """The waveform once it is read, or a message instead ("Llegint…", an error)."""
        self._peaks = peaks
        self._message = message
        self.update()

    @property
    def peaks(self) -> Peaks | None:
        return self._peaks

    # --- Geometry --------------------------------------------------------------------------------

    def _area(self) -> QRectF:
        margin = HANDLE_WIDTH
        return QRectF(margin, 2, max(1.0, self.width() - 2 * margin), max(1.0, self.height() - 4))

    def x_of(self, seconds: float) -> float:
        area = self._area()
        if self._duration <= 0:
            return area.left()
        return area.left() + area.width() * min(1.0, max(0.0, seconds / self._duration))

    def seconds_at(self, x: float) -> float:
        area = self._area()
        fraction = min(1.0, max(0.0, (x - area.left()) / area.width()))
        return round(fraction * self._duration / TRIM_STEP_S) * TRIM_STEP_S

    # --- Mouse -----------------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt)
        if event.button() != Qt.MouseButton.LeftButton or self._duration <= 0:
            return
        x = event.position().x()
        to_start, to_end = abs(x - self.x_of(self._start)), abs(x - self.x_of(self._end))
        if to_start == to_end:  # both handles in the same place: the side of the press decides
            self._dragging = "start" if x < self.x_of(self._start) else "end"
        else:
            self._dragging = "start" if to_start < to_end else "end"
        self._before_drag = (self._start, self._end)
        self._drag_to(x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt)
        if self._dragging is not None:
            self._drag_to(event.position().x())
        else:
            near = min(abs(event.position().x() - self.x_of(t)) for t in (self._start, self._end))
            self.setCursor(
                Qt.CursorShape.SizeHorCursor if near <= HANDLE_GRAB_PX else Qt.CursorShape.ArrowCursor
            )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt)
        if self._dragging is None:
            return
        self._drag_to(event.position().x())
        self._dragging = None
        if (self._start, self._end) != self._before_drag:
            self.trim_changed.emit(self._start, self._end)

    def _drag_to(self, x: float) -> None:
        seconds = self.seconds_at(x)
        if self._dragging == "start":
            start, end = min(seconds, self._end - TRIM_STEP_S), self._end
        else:
            start, end = self._start, max(seconds, self._start + TRIM_STEP_S)
        start, end = limit_trim(start, end, self._duration)
        if (start, end) != (self._start, self._end):
            self._start, self._end = start, end
            self.update()
            self.trim_moving.emit(start, end)

    # --- Drawing ---------------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt)
        painter = QPainter(self)
        area = self._area()
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Base))
        middle = area.center().y()
        peaks = self._peaks
        if peaks is not None and peaks.size:
            painter.setPen(QPen(WAVE_COLOUR, 1))
            step = area.width() / peaks.size
            half = area.height() / 2
            for i, peak in enumerate(peaks):
                x = area.left() + (i + 0.5) * step
                height = max(0.5, float(peak) * half)
                painter.drawLine(QPointF(x, middle - height), QPointF(x, middle + height))
        else:
            painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
            painter.drawLine(QPointF(area.left(), middle), QPointF(area.right(), middle))
            if self._message:
                painter.setPen(self.palette().color(QPalette.ColorRole.Text))
                painter.drawText(area, Qt.AlignmentFlag.AlignCenter, self._message)
        if self._duration > 0:
            left, right = self.x_of(self._start), self.x_of(self._end)
            painter.fillRect(
                QRectF(area.left(), area.top(), left - area.left(), area.height()), OUTSIDE_SHADE
            )
            painter.fillRect(QRectF(right, area.top(), area.right() - right, area.height()), OUTSIDE_SHADE)
            for x in (left, right):
                painter.fillRect(
                    QRectF(x - HANDLE_WIDTH / 2, 0, HANDLE_WIDTH, self.height()),
                    HANDLE_COLOUR,
                )
        painter.end()


def limit_trim(start: float, end: float, duration: float) -> tuple[float, float]:
    """Both ends inside the file and the start before the end (§1.7)."""
    end = min(max(0.0, end), duration)
    start = min(max(0.0, start), max(0.0, end - TRIM_STEP_S))
    return start, max(end, min(duration, start + TRIM_STEP_S))


# --- Reading the waveform ------------------------------------------------------------------------


UNEXPECTED_ERROR_KEY = "ffmpeg.unreadable"
"""Message shown when reading the waveform fails in an unexpected way."""


class _Signals(QObject):
    done = Signal(object, object, str)
    """path, peaks or None, message key of the error ("" when it went well)."""


class _Read(QRunnable):
    def __init__(self, path: Path, reader: WaveformReader, signals: _Signals) -> None:
        super().__init__()
        self._path = path
        self._reader = reader
        self._signals = signals

    def run(self) -> None:
        try:
            peaks = np.asarray(self._reader(self._path, WAVEFORM_POINTS), dtype=np.float32)
        except PassiMakerError as error:
            self._signals.done.emit(self._path, None, error.message_key)
            return
        except Exception:
            # Always answer: otherwise the path would stay "being read" for the whole session.
            _log.exception("Could not read the waveform of %s", self._path)
            self._signals.done.emit(self._path, None, UNEXPECTED_ERROR_KEY)
            return
        self._signals.done.emit(self._path, peaks, "")


class WaveformLoader(QObject):
    """Peaks of each song file, read once in a worker thread."""

    ready = Signal(object, object, str)
    """path, peaks (None if it could not be read) and the message key of the error."""

    def __init__(self, reader: WaveformReader = waveform, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._reader = reader
        self._peaks: dict[Path, Peaks] = {}
        self._errors: dict[Path, str] = {}
        self._pending: set[Path] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

    def known(self, path: Path) -> tuple[Peaks | None, str] | None:
        """(peaks, error key) if this file was already read, None otherwise."""
        if path in self._peaks:
            return self._peaks[path], ""
        if path in self._errors:
            return None, self._errors[path]
        return None

    def request(self, path: Path) -> None:
        """Reads the file unless it is known or already being read; answers with `ready`."""
        known = self.known(path)
        if known is not None:
            self.ready.emit(path, *known)
            return
        if path in self._pending:
            return
        self._pending.add(path)
        signals = _Signals(self)
        signals.done.connect(self._on_done)
        self._pool.start(_Read(path, self._reader, signals))

    def forget(self, path: Path) -> None:
        """The file may have changed (found again on disk): it is read again next time."""
        self._peaks.pop(path, None)
        self._errors.pop(path, None)

    def wait(self, milliseconds: int = 10_000) -> bool:
        return self._pool.waitForDone(milliseconds)

    def _on_done(self, path: object, peaks: object, error: str) -> None:
        if not isinstance(path, Path):
            return
        self._pending.discard(path)
        if isinstance(peaks, np.ndarray):
            self._peaks[path] = peaks
        else:
            self._errors[path] = error
        self.ready.emit(path, self._peaks.get(path), error)
