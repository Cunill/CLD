"""Fixed view of the selected photo: one composed frame, rendered off the GUI thread.

It is the placeholder of the preview area of §1.0 until block B13 brings the real player. It
uses the same compositor as the export (rule 3), so what is shown here is what the video will
have: encaix, moviment i format.
"""

from __future__ import annotations

import logging
import threading
from typing import cast

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QPainter, QPaintEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from passimaker.common import RGBImage
from passimaker.images import ImageSource
from passimaker.model import Change, Project, ProjectController
from passimaker.preview import PREVIEW_MAX_SIZE
from passimaker.render import Compositor, IntermediateProvider
from passimaker.timeline import Timeline, compute_timeline
from passimaker.ui.thumbnails import to_pixmap

_log = logging.getLogger(__name__)


class _Signals(QObject):
    done = Signal(int, object)


class _Render(QRunnable):
    def __init__(self, scene: _Scene, t: float, size: QSize, generation: int, signals: _Signals) -> None:
        super().__init__()
        self._scene = scene
        self._t = t
        self._size = size
        self._generation = generation
        self._signals = signals

    def run(self) -> None:
        try:
            frame = self._scene.compositor.frame_at(self._t, self._size.width(), self._size.height())
        except Exception:  # a still must never bring the window down
            _log.exception("no s'ha pogut dibuixar la vista fixa")
            return
        self._signals.done.emit(self._generation, frame)


class _Scene:
    """Timeline and compositor of one project snapshot (built once, used by the worker)."""

    def __init__(self, project: Project, images: ImageSource, intermediate: IntermediateProvider | None):
        self.project = project
        self.timeline: Timeline = compute_timeline(project)
        self.compositor = Compositor(project, self.timeline, images, intermediate)


class StillView(QWidget):
    """Draws the frame in the middle of the selected photo, letterboxed on black."""

    def __init__(
        self,
        controller: ProjectController,
        images: ImageSource,
        intermediate: IntermediateProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._images = images
        self._intermediate = intermediate
        self._scene: _Scene | None = None
        self._lock = threading.Lock()
        self._photo_id: str | None = None
        self._pixmap: QPixmap | None = None
        self._generation = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_frame)
        self._unsubscribe = controller.subscribe(self._on_changes)
        self.setMinimumSize(240, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(False)

    # --- Public ----------------------------------------------------------------------------------

    def show_photo(self, photo_id: str | None) -> None:
        if photo_id == self._photo_id:
            return
        self._photo_id = photo_id
        self.refresh()

    def refresh(self) -> None:
        """Renders again (after an edit or a resize)."""
        self._generation += 1
        if self._photo_id is None:
            self._pixmap = None
            self.update()
            return
        scene = self._scene_for(self._controller.project)
        moment = _middle_of(scene.timeline, self._photo_id)
        if moment is None:
            self._pixmap = None
            self.update()
            return
        self._pool.start(_Render(scene, moment, self._render_size(), self._generation, self._signals))

    def wait(self, milliseconds: int = 10_000) -> bool:
        """Waits for the render thread (tests and closing)."""
        return self._pool.waitForDone(milliseconds)

    @property
    def pixmap(self) -> QPixmap | None:
        return self._pixmap

    def close_view(self) -> None:
        self._unsubscribe()
        self._pool.waitForDone(5_000)

    # --- Internals -------------------------------------------------------------------------------

    def _scene_for(self, project: Project) -> _Scene:
        with self._lock:
            if self._scene is None or self._scene.project is not project:
                self._scene = _Scene(project, self._images, self._intermediate)
            return self._scene

    def _render_size(self) -> QSize:
        width, height = self._controller.project.output_format.size
        limit = min(
            max(1, self.width()) / width,
            max(1, self.height()) / height,
            PREVIEW_MAX_SIZE[0] / width,
            PREVIEW_MAX_SIZE[1] / height,
        )
        return QSize(max(16, round(width * limit)), max(16, round(height * limit)))

    def _on_frame(self, generation: int, frame: object) -> None:
        if generation != self._generation or not isinstance(frame, np.ndarray):
            return
        self._pixmap = to_pixmap(cast(RGBImage, frame))
        self.update()

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if changes - {Change.SAVED_STATE}:
            self.refresh()

    # --- Painting --------------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt)
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        pixmap = self._pixmap
        if pixmap is None or pixmap.isNull():
            return
        scaled = pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(
            (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self.refresh()


def _middle_of(timeline: Timeline, photo_id: str) -> float | None:
    """Middle of the photo's own space: there it is alone and fully opaque."""
    for slot in timeline.slots:
        if slot.photo_id == photo_id:
            return (slot.slot_start + slot.slot_end) / 2
    return None
