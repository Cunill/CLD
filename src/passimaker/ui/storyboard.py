"""The storyboard: a grid of thumbnails in show order (§1.2).

Only the visible cells are drawn (Qt asks the delegate for them) and only the visible photos ask
for a thumbnail, so a project with 1.000 photos opens as fast as one with ten.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from passimaker.model import Photo
from passimaker.ui.delegate import PADDING, TEXT_HEIGHT, PhotoDelegate, ThumbnailSize
from passimaker.ui.photos import PhotoListModel, PhotoRole
from passimaker.ui.thumbnails import ThumbnailBridge

SPACING = 4
VISIBLE_MARGIN_ROWS = 1
"""Rows of thumbnails asked for above and below the visible ones, so scrolling finds them ready."""
REQUEST_DELAY_MS = 30
"""Thumbnails are asked for this long after the last scroll event (a fast scroll asks once)."""
REPAINT_DELAY_MS = 16
"""Thumbnails that arrive together are repainted together (one frame at 60 Hz)."""


class StoryboardView(QListView):
    """Grid of thumbnails with selection, reordering by dragging and drops of files."""

    files_dropped = Signal(list, int)

    def __init__(
        self, model: PhotoListModel, thumbnails: ThumbnailBridge, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._thumbnails = thumbnails
        self._delegate = PhotoDelegate(thumbnails)
        self.setModel(model)
        self.setItemDelegate(self._delegate)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(SPACING)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._apply_grid()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REQUEST_DELAY_MS)
        self._timer.timeout.connect(self.request_visible_thumbnails)
        self._arrived: set[str] = set()
        self._repaint = QTimer(self)
        self._repaint.setSingleShot(True)
        self._repaint.setInterval(REPAINT_DELAY_MS)
        self._repaint.timeout.connect(self._flush_thumbnails)
        model.files_dropped.connect(self.files_dropped)
        model.modelReset.connect(self.schedule_thumbnails)
        thumbnails.ready.connect(self._on_thumbnail)
        self.verticalScrollBar().valueChanged.connect(self.schedule_thumbnails)

    # --- Thumbnail size --------------------------------------------------------------------------

    @property
    def thumbnail_size(self) -> ThumbnailSize:
        return self._delegate.size

    def set_thumbnail_size(self, size: ThumbnailSize) -> None:
        self._delegate.set_size(size)
        self._apply_grid()
        self.scheduleDelayedItemsLayout()
        self.viewport().update()

    def _apply_grid(self) -> None:
        side = self._delegate.size.value
        self.setGridSize(QSize(side + 2 * PADDING + SPACING, side + 2 * PADDING + TEXT_HEIGHT + SPACING))

    # --- Visible photos --------------------------------------------------------------------------

    def schedule_thumbnails(self) -> None:
        self._timer.start()

    def visible_rows(self) -> list[int]:
        """Rows whose cell touches the viewport, found by probing a grid of points on it."""
        viewport = self.viewport()
        model = self.model()
        if model.rowCount() == 0:
            return []
        grid = self.gridSize()
        step_x = max(1, grid.width() // 2)
        step_y = max(1, grid.height() // 2)
        rows: set[int] = set()
        for y in range(0, viewport.height() + step_y, step_y):
            for x in range(0, viewport.width() + step_x, step_x):
                index = self.indexAt(QPoint(min(x, viewport.width() - 1), min(y, viewport.height() - 1)))
                if index.isValid():
                    rows.add(index.row())
        return sorted(rows)

    def request_visible_thumbnails(self) -> None:
        rows = self.visible_rows()
        model = self.model()
        if not rows or not isinstance(model, PhotoListModel):
            return
        columns = max(1, self._columns())
        first = max(0, rows[0] - VISIBLE_MARGIN_ROWS * columns)
        last = min(model.rowCount() - 1, rows[-1] + VISIBLE_MARGIN_ROWS * columns)
        photos: list[Photo] = []
        for row in range(first, last + 1):
            photo = model.photo_at(row)
            if photo is not None:
                photos.append(photo)
        self._thumbnails.request(photos)

    def _columns(self) -> int:
        return max(1, self.viewport().width() // max(1, self.gridSize().width()))

    def _on_thumbnail(self, photo_id: str) -> None:
        """Thumbnails arrive in bursts: they are repainted together, not one by one."""
        self._arrived.add(photo_id)
        if not self._repaint.isActive():
            self._repaint.start()

    def _flush_thumbnails(self) -> None:
        arrived, self._arrived = self._arrived, set()
        model = self.model()
        if arrived and isinstance(model, PhotoListModel):
            model.refresh_photos(arrived)

    # --- Events ----------------------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self.schedule_thumbnails()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self.schedule_thumbnails()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 (Qt)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt)
        """Files dropped on the storyboard go in at the point where they are let go (§1.1)."""
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths, self.drop_row(event.position().toPoint()))
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def drop_row(self, position: QPoint) -> int:
        """Row a drop at this point lands on; -1 means "at the end"."""
        index = self.indexAt(position)
        if not index.isValid():
            return -1
        rect = self.visualRect(index)
        return index.row() + 1 if position.x() > rect.center().x() else index.row()

    # --- Selection -------------------------------------------------------------------------------

    def selected_rows(self) -> list[int]:
        return sorted(index.row() for index in self.selectionModel().selectedIndexes())

    def selected_ids(self) -> tuple[str, ...]:
        model = self.model()
        if not isinstance(model, PhotoListModel):
            return ()
        photos = [model.photo_at(row) for row in self.selected_rows()]
        return tuple(photo.id for photo in photos if photo is not None)

    def select_ids(self, photo_ids: Sequence[str]) -> None:
        model = self.model()
        selection = self.selectionModel()
        if not isinstance(model, PhotoListModel):
            return
        rows = [row for row in (model.row_of(photo_id) for photo_id in photo_ids) if row >= 0]
        chosen = QItemSelection()
        for row in rows:
            chosen.select(model.index(row, 0), model.index(row, 0))
        selection.select(chosen, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        if rows:
            selection.setCurrentIndex(model.index(rows[0], 0), QItemSelectionModel.SelectionFlag.NoUpdate)
            self.scrollTo(model.index(rows[0], 0), QAbstractItemView.ScrollHint.EnsureVisible)

    def current_photo(self) -> Photo | None:
        model = self.model()
        index: QModelIndex = self.currentIndex()
        if not index.isValid() or not isinstance(model, PhotoListModel):
            return None
        value = index.data(PhotoRole.PHOTO)
        return value if isinstance(value, Photo) else None


class StoryboardPanel(QStackedWidget):
    """The storyboard, or the empty state with the instructions of §1.0 when there is no photo."""

    choose_photos = Signal()

    def __init__(
        self, model: PhotoListModel, thumbnails: ThumbnailBridge, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.view = StoryboardView(model, thumbnails)
        self.empty = _EmptyState()
        self.empty.choose_photos.connect(self.choose_photos)
        self.addWidget(self.empty)
        self.addWidget(self.view)
        model.modelReset.connect(self.update_state)
        self.update_state()

    def update_state(self) -> None:
        has_photos = self.view.model().rowCount() > 0
        self.setCurrentWidget(self.view if has_photos else self.empty)


class _EmptyState(QWidget):
    """ "Arrossega aquí les fotos o la carpeta" and the [Tria fotos…] button (§1.0, step 1)."""

    choose_photos = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel(self.tr("Arrossega aquí les fotos o la carpeta"))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.label.font()
        font.setPointSize(max(10, font.pointSize() + 3))
        self.label.setFont(font)
        self.button = QPushButton(self.tr("Tria fotos…"))
        self.button.setObjectName("choosePhotos")
        self.button.clicked.connect(self.choose_photos)
        layout.addWidget(self.label)
        layout.addSpacing(12)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)
