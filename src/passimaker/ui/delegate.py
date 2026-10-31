"""How one photo is drawn in the storyboard (§1.2).

Qt only asks for the cells that are on screen, so with 1.000 photos this runs a few dozen times
per repaint. It never decodes anything: the pixmap comes from the thumbnail bridge, and while it
is not there the cell shows a plain placeholder.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from passimaker.model import MotionType
from passimaker.ui import icons
from passimaker.ui.formatting import duration as duration_text
from passimaker.ui.photos import PhotoRole
from passimaker.ui.thumbnails import ThumbnailBridge


class ThumbnailSize(Enum):
    """Thumbnail sizes of §1.2 (the side of the square the photo is drawn in, in pixels)."""

    SMALL = 96
    MEDIUM = 144
    LARGE = 208


PADDING = 6
TEXT_HEIGHT = 18
ICON_SIZE = 16


class PhotoDelegate(QStyledItemDelegate):
    def __init__(self, thumbnails: ThumbnailBridge, size: ThumbnailSize = ThumbnailSize.MEDIUM) -> None:
        super().__init__()
        self._thumbnails = thumbnails
        self._size = size

    @property
    def size(self) -> ThumbnailSize:
        return self._size

    def set_size(self, size: ThumbnailSize) -> None:
        self._size = size

    def sizeHint(  # noqa: N802 (Qt)
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        side = self._size.value
        return QSize(side + 2 * PADDING, side + 2 * PADDING + TEXT_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = option.palette  # pyright: ignore[reportAttributeAccessIssue]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)  # pyright: ignore[reportAttributeAccessIssue]
        rect: QRect = option.rect  # pyright: ignore[reportAttributeAccessIssue]
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette.color(QPalette.ColorRole.Highlight))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        box = QRect(rect.left() + PADDING, rect.top() + PADDING, self._size.value, self._size.value)
        if bool(index.data(PhotoRole.BLACK)):
            self._paint_black(painter, box)
        else:
            self._paint_image(painter, box, index, palette)
        self._paint_text(painter, rect, box, index, palette, selected)
        painter.restore()

    # --- Parts -----------------------------------------------------------------------------------

    def _paint_black(self, painter: QPainter, box: QRect) -> None:
        """A black slide (M08): a black card with a thin border, so it shows on a dark background."""
        painter.setPen(QColor(110, 110, 110))
        painter.setBrush(QColor(0, 0, 0))
        painter.drawRect(box.adjusted(0, 0, -1, -1))

    def _paint_image(
        self, painter: QPainter, box: QRect, index: QModelIndex | QPersistentModelIndex, palette: QPalette
    ) -> None:
        photo_id = str(index.data(PhotoRole.PHOTO_ID) or "")
        missing = bool(index.data(PhotoRole.MISSING))
        pixmap = None if missing else self._thumbnails.pixmap(photo_id)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(60, 60, 60) if pixmap is None else QColor(20, 20, 20))
        painter.drawRect(box)
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                box.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            target = QRect(
                box.left() + (box.width() - scaled.width()) // 2,
                box.top() + (box.height() - scaled.height()) // 2,
                scaled.width(),
                scaled.height(),
            )
            painter.drawPixmap(target, scaled)
        if missing or self._thumbnails.failed(photo_id):
            side = min(box.width(), box.height()) / 3
            centre = QRectF(box.center().x() - side / 2, box.center().y() - side / 2, side, side)
            icons.paint_warning(painter, centre, QColor(214, 142, 36))
            return
        self._paint_corner_icons(painter, box, index, palette)

    def _paint_corner_icons(
        self, painter: QPainter, box: QRect, index: QModelIndex | QPersistentModelIndex, palette: QPalette
    ) -> None:
        motion = index.data(PhotoRole.MOTION_TYPE)
        if isinstance(motion, MotionType) and motion is not MotionType.NONE:
            icons.paint_motion(painter, QRectF(box.left() + 3, box.top() + 3, ICON_SIZE, ICON_SIZE), motion)
        if bool(index.data(PhotoRole.LOW_RESOLUTION)):
            icons.paint_low_resolution(
                painter,
                QRectF(box.right() - ICON_SIZE - 3, box.top() + 3, ICON_SIZE, ICON_SIZE),
                QColor(255, 255, 255, 230),
            )

    def _paint_text(
        self,
        painter: QPainter,
        rect: QRect,
        box: QRect,
        index: QModelIndex | QPersistentModelIndex,
        palette: QPalette,
        selected: bool,
    ) -> None:
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        colour = palette.color(role)
        painter.setPen(colour)
        line = QRect(box.left(), box.bottom() + 2, box.width(), TEXT_HEIGHT)
        number = index.data(PhotoRole.NUMBER)
        painter.drawText(line, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), str(number))
        seconds = index.data(PhotoRole.DURATION_S)
        text = duration_text(float(seconds)) if isinstance(seconds, (int, float)) else ""
        dot = ICON_SIZE if bool(index.data(PhotoRole.CUSTOM_DURATION)) else 0
        painter.drawText(
            line.adjusted(0, 0, -dot, 0),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            text,
        )
        if dot:
            icons.paint_custom_duration(
                painter,
                QRectF(line.right() - ICON_SIZE, line.center().y() - ICON_SIZE / 2, ICON_SIZE, ICON_SIZE),
                colour,
            )
