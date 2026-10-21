"""Small icons drawn with QPainter (§1.2): motion type, custom duration, low resolution, missing.

They are painted instead of loaded so that the program keeps working from a single ZIP with no
image files, and so that they follow the palette of the current style.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from passimaker.model import MotionType

_ARROWS: dict[MotionType, tuple[float, float]] = {
    MotionType.PAN_LEFT: (-1.0, 0.0),
    MotionType.PAN_RIGHT: (1.0, 0.0),
    MotionType.PAN_UP: (0.0, -1.0),
    MotionType.PAN_DOWN: (0.0, 1.0),
}


def paint_badge(painter: QPainter, rect: QRectF, colour: QColor) -> None:
    """Round translucent background that keeps an icon readable over any photo."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawEllipse(rect)


def paint_motion(painter: QPainter, rect: QRectF, motion: MotionType) -> None:
    """An arrow for the pans, a square with arrows for the zooms, a dot for "no motion"."""
    painter.save()
    paint_badge(painter, rect, QColor(0, 0, 0, 120))
    pen = QPen(QColor(255, 255, 255, 230))
    pen.setWidthF(max(1.0, rect.width() / 10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    inner = rect.adjusted(rect.width() / 4, rect.height() / 4, -rect.width() / 4, -rect.height() / 4)
    centre = rect.center()
    if motion in _ARROWS:
        dx, dy = _ARROWS[motion]
        _arrow(painter, centre, dx, dy, rect.width() / 3)
    elif motion in (MotionType.ZOOM_IN, MotionType.ZOOM_OUT, MotionType.COMBINED):
        painter.drawRect(inner)
        if motion is not MotionType.ZOOM_OUT:
            painter.drawLine(inner.topLeft(), rect.topLeft() + QPointF(rect.width() / 8, rect.height() / 8))
            painter.drawLine(
                inner.bottomRight(), rect.bottomRight() - QPointF(rect.width() / 8, rect.height() / 8)
            )
    else:
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawEllipse(centre, rect.width() / 10, rect.width() / 10)
    painter.restore()


def _arrow(painter: QPainter, centre: QPointF, dx: float, dy: float, length: float) -> None:
    tip = QPointF(centre.x() + dx * length, centre.y() + dy * length)
    tail = QPointF(centre.x() - dx * length, centre.y() - dy * length)
    painter.drawLine(tail, tip)
    side = QPointF(-dy, dx) * (length / 2)
    back = QPointF(tip.x() - dx * length / 2, tip.y() - dy * length / 2)
    painter.drawPolyline(QPolygonF([back + side, tip, back - side]))


def paint_warning(painter: QPainter, rect: QRectF, colour: QColor) -> None:
    """Triangle with an exclamation mark: the file of the photo is not there (§1.2)."""
    painter.save()
    path = QPainterPath()
    path.moveTo(rect.center().x(), rect.top())
    path.lineTo(rect.bottomRight())
    path.lineTo(rect.bottomLeft())
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawPath(path)
    pen = QPen(QColor(255, 255, 255))
    pen.setWidthF(max(1.0, rect.width() / 10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    top = rect.top() + rect.height() * 0.4
    bottom = rect.bottom() - rect.height() * 0.3
    painter.drawLine(QPointF(rect.center().x(), top), QPointF(rect.center().x(), bottom))
    painter.drawPoint(QPointF(rect.center().x(), rect.bottom() - rect.height() * 0.15))
    painter.restore()


def paint_low_resolution(painter: QPainter, rect: QRectF, colour: QColor) -> None:
    """Four big "pixels": the photo is small and the motion had to be reduced (§1.1)."""
    painter.save()
    paint_badge(painter, rect, QColor(0, 0, 0, 120))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    side = rect.width() / 4
    origin = rect.center() - QPointF(side, side)
    for row in range(2):
        for column in range(2):
            if (row + column) % 2 == 0:
                painter.drawRect(QRectF(origin.x() + column * side, origin.y() + row * side, side, side))
    painter.restore()


def paint_custom_duration(painter: QPainter, rect: QRectF, colour: QColor) -> None:
    """The filled dot of the layout of §1.0 ("7,0s●"): this photo has its own duration."""
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawEllipse(rect.center(), rect.width() / 4, rect.width() / 4)
    painter.restore()
