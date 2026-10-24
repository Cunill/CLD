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
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QResizeEvent,
    QShowEvent,
)
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
from passimaker.ui.photos import PHOTO_MIME, PhotoListModel, PhotoRole
from passimaker.ui.thumbnails import ThumbnailBridge

SPACING = 4
VISIBLE_MARGIN_ROWS = 1
"""Rows of thumbnails asked for above and below the visible ones, so scrolling finds them ready."""
REQUEST_DELAY_MS = 30
"""Thumbnails are asked for this long after the last scroll event (a fast scroll asks once)."""
REPAINT_DELAY_MS = 16
"""Thumbnails that arrive together are repainted together (one frame at 60 Hz)."""
INSERTION_LINE_WIDTH = 3
"""Width in pixels of the vertical line that shows where dragged photos or files will go (§1.2)."""


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
        # setMovement(Static) also stops the viewport (where the thumbnails are) from taking drops:
        # without this line, a dragged photo went over to the window, which only takes files (M04).
        self.viewport().setAcceptDrops(True)
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
        self._insert_row: int | None = None
        """Where a drag over the grid would let go (-1 = at the end); None when nothing is dragged."""
        self._insert_y = 0
        """Height of the cursor during the drag: it decides on which line of the grid the line goes."""
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

    # Qt's grid of icons with fixed places (IconMode + Movement.Static) neither accepts a drag of its
    # own items nor draws where they would go, so the photos being reordered are handled here: the
    # grid accepts them, draws the insertion line, scrolls near the top and bottom edges and lets go
    # through the model (which asks the controller).

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._show_insertion(event.position().toPoint())
            return
        super().dragEnterEvent(event)
        self._accept_photos(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 (Qt)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._show_insertion(event.position().toPoint())
            return
        super().dragMoveEvent(event)
        self._accept_photos(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 (Qt)
        super().dragLeaveEvent(event)
        self._hide_insertion()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt)
        """Files dropped on the storyboard go in at the point where they are let go (§1.1)."""
        row = self.drop_row(event.position().toPoint())
        self._hide_insertion()
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths, row)
                event.acceptProposedAction()
                return
        if event.mimeData().hasFormat(PHOTO_MIME):
            model = self.model()
            target = row if row >= 0 else model.rowCount()
            model.dropMimeData(event.mimeData(), Qt.DropAction.MoveAction, target, 0, QModelIndex())
            # Reported as a copy: after a move, Qt would try to remove the dragged rows itself,
            # and the controller has already put them in their new place.
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.stopAutoScroll()
            self.setState(QAbstractItemView.State.NoState)
            return
        super().dropEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt)
        super().paintEvent(event)
        line = self.insertion_line()
        if line is not None:
            painter = QPainter(self.viewport())
            painter.fillRect(line, self.palette().color(QPalette.ColorRole.Highlight))
            painter.end()

    def insertion_line(self) -> QRect | None:
        """The vertical line drawn while dragging: before the photo the drop would land on, or after
        the previous one when that is the one under the cursor (the end of a line of the grid)."""
        model = self.model()
        count = model.rowCount()
        if self._insert_row is None or count == 0:
            return None
        row = self._insert_row if 0 <= self._insert_row < count else count
        before = self.visualRect(model.index(row, 0)) if row < count else None
        after = self.visualRect(model.index(row - 1, 0)) if row > 0 else None
        if after is not None and (before is None or after.top() <= self._insert_y <= after.bottom()):
            return QRect(after.right() + 1, after.top(), INSERTION_LINE_WIDTH, after.height())
        assert before is not None
        return QRect(
            before.left() - INSERTION_LINE_WIDTH + 1, before.top(), INSERTION_LINE_WIDTH, before.height()
        )

    def _accept_photos(self, event: QDragMoveEvent) -> None:
        if not event.mimeData().hasFormat(PHOTO_MIME):
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        position = event.position().toPoint()
        self._show_insertion(position)
        margin = self.autoScrollMargin()
        if position.y() < margin or position.y() > self.viewport().height() - margin:
            self.startAutoScroll()  # Qt may have skipped it for a drag of its own items

    def _show_insertion(self, position: QPoint) -> None:
        row = self.drop_row(position)
        if row != self._insert_row or position.y() != self._insert_y:
            self._insert_row = row
            self._insert_y = position.y()
            self.viewport().update()

    def _hide_insertion(self) -> None:
        if self._insert_row is not None:
            self._insert_row = None
            self.viewport().update()

    def drop_row(self, position: QPoint) -> int:
        """Row a drop at this point lands on; -1 means "at the end".

        Between two photos, or in the empty space after the last photo of a line of the grid, it is
        the place after the nearest photo on the left (where the insertion line is drawn).
        """
        index = self.indexAt(position)
        if index.isValid():
            rect = self.visualRect(index)
            return index.row() + 1 if position.x() > rect.center().x() else index.row()
        step = max(1, self.gridSize().width() // 4)
        probe = QPoint(position.x() - step, position.y())
        while probe.x() >= 0:
            on_the_left = self.indexAt(probe)
            if on_the_left.isValid():
                return on_the_left.row() + 1
            probe.setX(probe.x() - step)
        on_the_right = self.indexAt(QPoint(position.x() + step, position.y()))
        return on_the_right.row() if on_the_right.isValid() else -1

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


STEPS_MIN_WIDTH = 420
"""The hint of the empty state wraps in two lines, not in a narrow column."""


class _EmptyState(QWidget):
    """ "Arrossega aquí les fotos o la carpeta", the [Tria fotos…] button (§1.0, step 1) and a hint
    with the three steps (B16)."""

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
        self.steps = QLabel(
            self.tr(
                "Un passi es fa en tres passos: <b>Fotos</b> → <b>Música</b> → <b>Exportar vídeo</b>.<br>"
                "Tota la resta ja té valors pensats perquè quedi bé.<br>"
                "Ajuda ▸ Guia d'ús (F1) ho explica tot."
            )
        )
        self.steps.setObjectName("emptySteps")
        self.steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.steps.setWordWrap(True)
        self.steps.setMinimumWidth(STEPS_MIN_WIDTH)
        self.steps.setTextFormat(Qt.TextFormat.RichText)
        self.steps.setEnabled(False)  # the grey of a hint, under the main instruction
        layout.addWidget(self.label)
        layout.addSpacing(12)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(self.steps)
