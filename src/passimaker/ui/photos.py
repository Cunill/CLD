"""Qt model over the project photos (§1.2).

The project is immutable and only the controller changes it (rule 2), so this model is a thin
read-only view: every edit it is asked for (a drag, a drop of files) becomes a command.

One row per slide: the black slides (M08) are the first and the last rows. They cannot be dragged,
and drops land between them, so the rows are turned into photo indices for the commands.
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

from passimaker.model import BlackSlide, BlackSlidePosition, Change, Photo, ProjectController, Slide
from passimaker.model.commands import MovePhotos

PHOTO_MIME = "application/x-passimaker-photos"
"""Internal drag: the ids of the photos being moved, one per line."""

type AnyIndex = QModelIndex | QPersistentModelIndex

_NO_PARENT = QModelIndex()
"""Qt's "no parent" index; a list model has no hierarchy."""


def _rows_of(slides: tuple[Slide, ...]) -> dict[str, int]:
    return {slide.id: row for row, slide in enumerate(slides)}


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
    """The Photo, or the BlackSlide of a black row."""
    BLACK = int(Qt.ItemDataRole.UserRole) + 8


class PhotoListModel(QAbstractListModel):
    """Slides of the project (photos and black slides), in show order. Rows are rebuilt when the
    controller says so."""

    files_dropped = Signal(list, int)
    """Paths dropped on the storyboard and the row they were dropped at (-1 = at the end)."""

    def __init__(self, controller: ProjectController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._slides: tuple[Slide, ...] = controller.project.slides
        self._photos: tuple[Photo, ...] = controller.project.photos
        self._rows: dict[str, int] = _rows_of(self._slides)
        self._missing: frozenset[str] = frozenset()
        self._unsubscribe = controller.subscribe(self._on_changes)

    # --- Reading ---------------------------------------------------------------------------------

    def photos(self) -> tuple[Photo, ...]:
        return self._photos

    def slide_at(self, row: int) -> Slide | None:
        return self._slides[row] if 0 <= row < len(self._slides) else None

    def photo_at(self, row: int) -> Photo | None:
        """None for a black slide too."""
        slide = self.slide_at(row)
        return slide if isinstance(slide, Photo) else None

    def first_photo_row(self) -> int:
        """1 when the show starts with a black slide, else 0."""
        return 1 if self._slides and isinstance(self._slides[0], BlackSlide) else 0

    def photo_index(self, row: int) -> int:
        """The photo index (as AddPhotos and MovePhotos take it) of a drop at this row (-1 = at the
        end): always between the black slides."""
        count = len(self._photos)
        return count if row < 0 else min(count, max(0, row - self.first_photo_row()))

    def drop_row(self, row: int) -> int:
        """The row a drop at this row (-1 = at the end) really goes to: never outside the black slides.
        Without a black slide at the end, -1 stays -1."""
        if row < 0 and not (self._slides and isinstance(self._slides[-1], BlackSlide)):
            return row
        return self.first_photo_row() + self.photo_index(row)

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
        return 0 if parent.isValid() else len(self._slides)

    def data(self, index: AnyIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        slide = self.slide_at(index.row()) if index.isValid() else None
        if isinstance(slide, BlackSlide):
            return self._black_data(slide, role)
        photo = slide
        if photo is None:
            return None
        match role:
            case PhotoRole.PHOTO_ID:
                return photo.id
            case PhotoRole.PHOTO:
                return photo
            case PhotoRole.BLACK:
                return False
            case PhotoRole.NUMBER:
                return index.row() + 1 - self.first_photo_row()
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

    def _black_data(self, slide: BlackSlide, role: int) -> object:
        match role:
            case PhotoRole.PHOTO_ID:
                return slide.id
            case PhotoRole.PHOTO:
                return slide
            case PhotoRole.BLACK:
                return True
            case PhotoRole.NUMBER:
                return self.tr("Negre")
            case PhotoRole.DURATION_S:
                return slide.duration_s
            case PhotoRole.CUSTOM_DURATION | PhotoRole.LOW_RESOLUTION | PhotoRole.MISSING:
                return False
            case Qt.ItemDataRole.ToolTipRole:
                if slide.position is BlackSlidePosition.START:
                    return self.tr("Negre a l'inici del passi")
                return self.tr("Negre al final del passi")
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
        draggable = index.isValid() and self.photo_at(index.row()) is not None  # black slides stay put
        return base | Qt.ItemFlag.ItemIsDragEnabled if draggable else base

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802 (Qt)
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:  # noqa: N802 (Qt)
        return [PHOTO_MIME, "text/uri-list"]

    def mimeData(self, indexes: Sequence[AnyIndex]) -> QMimeData:  # noqa: N802 (Qt)
        photos = (self.photo_at(i.row()) for i in indexes if i.isValid())
        ids = [photo.id for photo in photos if photo is not None]
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
        target = self.photo_index(row if row >= 0 else (parent.row() if parent.isValid() else -1))
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
        """Reorders through the controller (target: a photo index); the model is rebuilt by the change
        notification."""
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
            self._slides = self._controller.project.slides
            self._photos = self._controller.project.photos
            self._rows = _rows_of(self._slides)
            self.endResetModel()
        elif changes & {Change.TIMING, Change.MOTION, Change.SETTINGS}:
            self._slides = self._controller.project.slides
            self._photos = self._controller.project.photos
            self._refresh_all()

    def _refresh_all(self) -> None:
        if self._slides:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._slides) - 1, 0))

    def close(self) -> None:
        self._unsubscribe()
