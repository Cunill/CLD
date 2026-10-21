"""Qt model over the project photos (§1.2).

The project is immutable and only the controller changes it (rule 2), so this model is a thin
read-only view: every edit it is asked for (a drag, a drop of files) becomes a command.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import IntEnum
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QMimeData,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)

from passimaker.model import Change, Photo, ProjectController
from passimaker.model.commands import MovePhotos

PHOTO_MIME = "application/x-passimaker-photos"
"""Internal drag: the ids of the photos being moved, one per line."""

type AnyIndex = QModelIndex | QPersistentModelIndex

_NO_PARENT = QModelIndex()
"""Qt's "no parent" index; a list model has no hierarchy."""


def _rows_of(photos: tuple[Photo, ...]) -> dict[str, int]:
    return {photo.id: row for row, photo in enumerate(photos)}


class PhotoRole(IntEnum):
    """Roles the delegate reads (Qt.UserRole and up)."""

    PHOTO_ID = int(Qt.ItemDataRole.UserRole)
    NUMBER = int(Qt.ItemDataRole.UserRole) + 1
    DURATION_S = int(Qt.ItemDataRole.UserRole) + 2
    CUSTOM_DURATION = int(Qt.ItemDataRole.UserRole) + 3
    MOTION_TYPE = int(Qt.ItemDataRole.UserRole) + 4
    LOW_RESOLUTION = int(Qt.ItemDataRole.UserRole) + 5
    MISSING = int(Qt.ItemDataRole.UserRole) + 6
    PHOTO = int(Qt.ItemDataRole.UserRole) + 7


class PhotoListModel(QAbstractListModel):
    """Photos of the project, in show order. Rows are rebuilt when the controller says so."""

    files_dropped = Signal(list, int)
    """Paths dropped on the storyboard and the row they were dropped at (-1 = at the end)."""

    def __init__(self, controller: ProjectController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._photos: tuple[Photo, ...] = controller.project.photos
        self._rows: dict[str, int] = _rows_of(self._photos)
        self._missing: frozenset[str] = frozenset()
        self._unsubscribe = controller.subscribe(self._on_changes)

    # --- Reading ---------------------------------------------------------------------------------

    def photos(self) -> tuple[Photo, ...]:
        return self._photos

    def photo_at(self, row: int) -> Photo | None:
        return self._photos[row] if 0 <= row < len(self._photos) else None

    def row_of(self, photo_id: str) -> int:
        """O(1): with a thousand photos this is asked for on every thumbnail that arrives."""
        return self._rows.get(photo_id, -1)

    def set_missing(self, photo_ids: frozenset[str]) -> None:
        """Photos whose file was not found (grey thumbnail with an icon, §1.2)."""
        if photo_ids == self._missing:
            return
        self._missing = photo_ids
        self._refresh_all()

    def rowCount(self, parent: AnyIndex = _NO_PARENT) -> int:  # noqa: N802 (Qt)
        return 0 if parent.isValid() else len(self._photos)

    def data(self, index: AnyIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        photo = self.photo_at(index.row()) if index.isValid() else None
        if photo is None:
            return None
        match role:
            case PhotoRole.PHOTO_ID:
                return photo.id
            case PhotoRole.PHOTO:
                return photo
            case PhotoRole.NUMBER:
                return index.row() + 1
            case PhotoRole.DURATION_S:
                return self._controller.project.photo_duration(photo)
            case PhotoRole.CUSTOM_DURATION:
                return photo.duration_s is not None
            case PhotoRole.MOTION_TYPE:
                return photo.motion.type
            case PhotoRole.LOW_RESOLUTION:
                return photo.low_resolution
            case PhotoRole.MISSING:
                return photo.id in self._missing
            case Qt.ItemDataRole.ToolTipRole:
                return str(photo.path)
            case _:
                return None

    def refresh_photos(self, photo_ids: Iterable[str]) -> None:
        """Repaints these rows (thumbnails that arrived), in one go when they are together."""
        rows = sorted(row for row in (self.row_of(photo_id) for photo_id in photo_ids) if row >= 0)
        if not rows:
            return
        self.dataChanged.emit(self.index(rows[0], 0), self.index(rows[-1], 0))

    # --- Dragging and dropping -------------------------------------------------------------------

    def flags(self, index: AnyIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDropEnabled
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802 (Qt)
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:  # noqa: N802 (Qt)
        return [PHOTO_MIME, "text/uri-list"]

    def mimeData(self, indexes: Sequence[AnyIndex]) -> QMimeData:  # noqa: N802 (Qt)
        ids = [self._photos[i.row()].id for i in indexes if i.isValid()]
        data = QMimeData()
        data.setData(PHOTO_MIME, "\n".join(ids).encode("utf-8"))
        return data

    def canDropMimeData(  # noqa: N802 (Qt)
        self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: AnyIndex
    ) -> bool:
        return data.hasFormat(PHOTO_MIME) or data.hasUrls()

    def dropMimeData(  # noqa: N802 (Qt)
        self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: AnyIndex
    ) -> bool:
        if action == Qt.DropAction.IgnoreAction:
            return True
        target = row if row >= 0 else (parent.row() if parent.isValid() else len(self._photos))
        if data.hasFormat(PHOTO_MIME):
            carried = data.data(PHOTO_MIME).toStdString()
            return self._move(carried.split("\n"), target)
        if data.hasUrls():
            paths = [Path(url.toLocalFile()) for url in data.urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths, target)
            return bool(paths)
        return False

    def _move(self, photo_ids: Sequence[str], target: int) -> bool:
        """Reorders through the controller; the model is rebuilt by the change notification."""
        known = {p.id for p in self._photos}
        moving = tuple(pid for pid in photo_ids if pid in known)
        if not moving:
            return False
        self._controller.execute(MovePhotos(moving, target))
        return False
        # False: the view must not remove the dragged rows itself (the controller already did).

    # --- Controller ------------------------------------------------------------------------------

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if Change.PHOTOS in changes:
            self.beginResetModel()
            self._photos = self._controller.project.photos
            self._rows = _rows_of(self._photos)
            self.endResetModel()
        elif changes & {Change.TIMING, Change.MOTION, Change.SETTINGS}:
            self._photos = self._controller.project.photos
            self._refresh_all()

    def _refresh_all(self) -> None:
        if self._photos:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._photos) - 1, 0))

    def close(self) -> None:
        self._unsubscribe()
