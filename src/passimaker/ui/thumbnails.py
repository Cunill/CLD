"""Bridge between the thumbnail service (plain threads, NumPy) and Qt.

``ThumbnailService`` (B5) answers from a worker thread; Qt widgets may only be touched from the
GUI thread. ``ThumbnailBridge`` receives the callback in the worker, hands the image over with a
queued signal and builds the ``QPixmap`` on the GUI thread, where it caches it by photo id.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from typing import Protocol, cast

import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap

from passimaker.common import RGBImage
from passimaker.model.types import Photo
from passimaker.thumbs import Priority, ThumbnailCallback

MAX_CACHED = 600
"""Thumbnails kept in memory (about 120 MB at 256 px). With a thousand photos the ones that
have been off screen longest are dropped and asked for again when they come back."""


class ThumbnailProvider(Protocol):
    """What the interface needs from ``passimaker.thumbs.ThumbnailService`` (B5)."""

    def request_thumbnail(self, photo: Photo, priority: Priority, callback: ThumbnailCallback) -> None: ...

    def get_intermediate(self, photo: Photo) -> RGBImage: ...

    def cancel_pending(self) -> None: ...

    def close(self) -> None: ...


def to_pixmap(image: RGBImage) -> QPixmap:
    """Copies a read-only RGB array into a QPixmap (GUI thread only)."""
    data = np.ascontiguousarray(image)
    height, width = data.shape[:2]
    raw = data.tobytes()  # kept in a name: QImage does not own the buffer, QPixmap copies it
    picture = QImage(raw, width, height, 3 * width, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(picture)


class ThumbnailBridge(QObject):
    """Requests thumbnails and emits ``ready(photo_id)`` once the pixmap is in the cache.

    - ``request`` is cheap and may be called for every visible photo on every scroll: a photo
      already asked for is not asked again until ``forget`` or ``clear``.
    - ``pixmap`` returns None while the thumbnail is not ready (the delegate draws a placeholder).
    - Failures are remembered too, so a broken photo is not retried on every scroll.
    """

    ready = Signal(str)
    _arrived = Signal(str, object)

    def __init__(self, service: ThumbnailProvider, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._pixmaps: OrderedDict[str, QPixmap] = OrderedDict()
        self._asked: set[str] = set()
        self._failed: set[str] = set()
        self._arrived.connect(self._store, Qt.ConnectionType.QueuedConnection)

    def pixmap(self, photo_id: str) -> QPixmap | None:
        found = self._pixmaps.get(photo_id)
        if found is not None:
            self._pixmaps.move_to_end(photo_id)
        return found

    @property
    def cached_count(self) -> int:
        """Thumbnails currently in memory (at most MAX_CACHED)."""
        return len(self._pixmaps)

    def failed(self, photo_id: str) -> bool:
        return photo_id in self._failed

    def request(self, photos: Sequence[Photo], priority: Priority = Priority.VISIBLE) -> None:
        for photo in photos:
            if photo.id in self._asked:
                continue
            self._asked.add(photo.id)
            self._service.request_thumbnail(photo, priority, self._deliver)

    def forget(self, photo_ids: frozenset[str]) -> None:
        """Drops what is known about these photos (after a rotation, or when they are removed)."""
        for photo_id in photo_ids:
            self._pixmaps.pop(photo_id, None)
            self._asked.discard(photo_id)
            self._failed.discard(photo_id)

    def clear(self) -> None:
        self._pixmaps.clear()
        self._asked.clear()
        self._failed.clear()

    def _deliver(self, photo_id: str, image: RGBImage | None) -> None:
        """Worker thread: hands the image over to the GUI thread."""
        self._arrived.emit(photo_id, image)

    def _store(self, photo_id: str, image: object) -> None:
        """GUI thread: builds the pixmap and tells the view that this photo changed."""
        if isinstance(image, np.ndarray):
            self._pixmaps[photo_id] = to_pixmap(cast(RGBImage, image))
            self._pixmaps.move_to_end(photo_id)
            while len(self._pixmaps) > MAX_CACHED:
                dropped, _ = self._pixmaps.popitem(last=False)
                self._asked.discard(dropped)
        else:
            self._failed.add(photo_id)
        self.ready.emit(photo_id)
