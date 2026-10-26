"""The waves of the "Grava el que sona" window (ESPECIFICACIO §1.7 ter "Ones", annex PLA_GRAVACIO §2.4).

- One lane per recorded channel (E and D in stereo, one lane for a mono source), with the level
  meter of that channel in dBFS beside it and a clipping mark that stays lit RECORD_CLIP_HOLD_S.
- Live: the last RECORD_WAVE_WINDOW_S scroll from right to left, grey before recording (to check
  that sound arrives) and red while recording. A QTimer at RECORD_WAVE_REFRESH_HZ collects only the
  new columns (peaks_since) and repaints; the core computes them in its capture thread (rule 6).
- After stopping: the whole recording reduced to the width of the wave, with the silence that is
  trimmed at both ends shaded (the wave is from before trimming and normalising).
- The waves do nothing else: no clicks, no selection.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QLineF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from passimaker.model import defaults
from passimaker.recorder import PeakColumns

LIVE_COLUMNS = round(defaults.RECORD_WAVE_WINDOW_S * defaults.RECORD_PEAK_COLUMNS_PER_S)
"""Columns of the live wave: the last RECORD_WAVE_WINDOW_S (500)."""
METER_FLOOR_DBFS = -60.0
"""The left end of the level meter; quieter is an empty meter."""
CLIP_DBFS = -0.01
"""A peak at 0 dBFS (or rounding a hair below it) lights the clipping mark."""
LANE_LABEL_WIDTH = 18
METER_TEXT_WIDTH = 52
METER_WIDTH = 110
CLIP_MARK_WIDTH = 8
LANE_HEIGHT = 44
LANE_GAP = 6
MARGIN = 4

IDLE_COLOR = QColor("#8a8a8a")
"""Before recording (and while waiting for the first sound): only shows that sound arrives."""
RECORDING_COLOR = QColor("#d03030")
OVERVIEW_COLOR = QColor("#2f5d8a")
"""The whole recording after stopping."""
TRIMMED_SHADE = QColor(0, 0, 0, 90)
"""Over the silence that is trimmed when saving."""
LANE_BACKGROUND = QColor("#f2f2f2")
CENTRE_LINE = QColor("#c8c8c8")
METER_BACKGROUND = QColor("#dddddd")
METER_COLOR = QColor("#3a9a3a")
METER_HOT_COLOR = QColor("#d8a020")
METER_HOT_DBFS = -6.0
CLIP_OFF_COLOR = QColor("#bbbbbb")
CLIP_ON_COLOR = QColor("#e01010")
TEXT_COLOR = QColor("#333333")

DB_SYMBOL = " dB"
"""Unit symbol, not prose (like formatting.SECONDS_SYMBOL)."""


class WaveSource(Protocol):
    """What the view follows: passimaker.recorder.Monitor or Recorder (contract §16)."""

    @property
    def level_dbfs(self) -> tuple[float, ...]: ...

    def peaks_since(self, index: int) -> tuple[PeakColumns, int]: ...


class WaveMode(Enum):
    LIVE = "live"
    OVERVIEW = "overview"


def meter_fraction(level_dbfs: float) -> float:
    """How much of the meter a level fills: 0 at METER_FLOOR_DBFS or below, 1 at 0 dBFS."""
    if math.isnan(level_dbfs) or level_dbfs <= METER_FLOOR_DBFS:
        return 0.0
    return min(1.0, (level_dbfs - METER_FLOOR_DBFS) / -METER_FLOOR_DBFS)


def level_text(level_dbfs: float) -> str:
    """ "-6 dB"; a dash for silence (the meter is empty)."""
    if math.isnan(level_dbfs) or level_dbfs <= METER_FLOOR_DBFS:
        return "–" + DB_SYMBOL
    return f"{min(0.0, level_dbfs):.0f}{DB_SYMBOL}".replace("-0 dB", "0 dB")


def column_lines(columns: PeakColumns, channel: int, rect: QRectF, slots: int) -> list[QLineF]:
    """One vertical line per column, from its minimum to its maximum, the last column at the
    right edge of `rect`; `slots` columns fill the whole width."""
    count = columns.shape[0]
    if count == 0 or slots <= 0:
        return []
    step = rect.width() / slots
    offsets: NDArray[np.float64] = np.arange(count - 1, -1, -1, dtype=np.float64) + 0.5
    xs = rect.right() - offsets * step
    centre = rect.center().y()
    half = rect.height() / 2
    lows = centre - np.clip(columns[:, channel, 0], -1.0, 1.0) * half
    highs = centre - np.clip(columns[:, channel, 1], -1.0, 1.0) * half
    # A silent column still shows as a dot on the centre line.
    highs = np.minimum(highs, lows - 0.5)
    return [
        QLineF(x, low, x, high)
        for x, low, high in zip(xs.tolist(), lows.tolist(), highs.tolist(), strict=True)
    ]


class WaveView(QWidget):
    def __init__(self, parent: QWidget | None = None, *, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(parent)
        self._clock = clock
        """For the clipping mark (the tests move time on)."""
        self._channels = 2
        self._mode = WaveMode.LIVE
        self._recording = False
        self._live: PeakColumns = np.zeros((0, self._channels, 2), dtype=np.float32)
        self._overview: PeakColumns = np.zeros((0, self._channels, 2), dtype=np.float32)
        self._trimmed: tuple[float, float] = (0.0, 0.0)
        self._levels: tuple[float, ...] = (-math.inf,) * self._channels
        self._clip_until: list[float] = [-math.inf] * self._channels
        self._source: WaveSource | None = None
        self._index = 0
        self.last_paint_s = 0.0
        """How long the last paintEvent took (the performance test reads it)."""
        self._timer = QTimer(self)
        self._timer.setInterval(round(1000 / defaults.RECORD_WAVE_REFRESH_HZ))
        self._timer.timeout.connect(self.refresh)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._height_for(self._channels))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(self.tr("Ones de cada canal: grises abans de gravar, vermelles mentre es grava"))

    # --- State, for the window and the tests ------------------------------------------------------

    @property
    def channels(self) -> int:
        """Lanes: 1 for a mono source, otherwise 2."""
        return self._channels

    @property
    def mode(self) -> WaveMode:
        return self._mode

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def following(self) -> bool:
        return self._source is not None

    @property
    def live_columns(self) -> PeakColumns:
        return self._live

    @property
    def levels(self) -> tuple[float, ...]:
        return self._levels

    @property
    def trimmed_fractions(self) -> tuple[float, float]:
        """Of the overview, the parts shaded at the start and at the end (0-1 of the width)."""
        return self._trimmed

    def wave_color(self) -> QColor:
        if self._mode is WaveMode.OVERVIEW:
            return OVERVIEW_COLOR
        return RECORDING_COLOR if self._recording else IDLE_COLOR

    def clipping(self, channel: int) -> bool:
        """The clipping mark of `channel` is lit (it lasts RECORD_CLIP_HOLD_S after a peak at 0 dBFS)."""
        return self._clock() < self._clip_until[channel]

    def lane_rect(self, channel: int) -> QRectF:
        """Where the wave of `channel` is painted."""
        left = MARGIN + LANE_LABEL_WIDTH
        right = self.width() - MARGIN - METER_TEXT_WIDTH - METER_WIDTH - CLIP_MARK_WIDTH - 3 * LANE_GAP
        top = MARGIN + channel * (LANE_HEIGHT + LANE_GAP)
        return QRectF(left, top, max(1.0, right - left), LANE_HEIGHT)

    def wave_width(self) -> int:
        """Pixels of a lane: the columns the overview needs."""
        return max(1, int(self.lane_rect(0).width()))

    def shaded_rects(self, channel: int = 0) -> list[QRectF]:
        """The trimmed silence of the overview, as painted over `channel`'s lane."""
        if self._mode is not WaveMode.OVERVIEW:
            return []
        rect = self.lane_rect(channel)
        start, end = self._trimmed
        shades: list[QRectF] = []
        if start > 0:
            shades.append(QRectF(rect.left(), rect.top(), rect.width() * start, rect.height()))
        if end > 0:
            width = rect.width() * end
            shades.append(QRectF(rect.right() - width, rect.top(), width, rect.height()))
        return shades

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(640, self._height_for(self._channels))

    # --- Feeding ----------------------------------------------------------------------------------

    def set_channels(self, channels: int) -> None:
        """A new source: `channels` lanes (1 or 2), empty."""
        self._channels = max(1, min(2, channels))
        self.setFixedHeight(self._height_for(self._channels))
        self.clear()

    def clear(self) -> None:
        self._mode = WaveMode.LIVE
        self._live = np.zeros((0, self._channels, 2), dtype=np.float32)
        self._overview = np.zeros((0, self._channels, 2), dtype=np.float32)
        self._trimmed = (0.0, 0.0)
        self._levels = (-math.inf,) * self._channels
        self._clip_until = [-math.inf] * self._channels
        self.update()

    def follow(self, source: WaveSource, *, recording: bool = False) -> None:
        """Show `source` live, collecting its new columns RECORD_WAVE_REFRESH_HZ times per second."""
        if source is not self._source:
            self._source = source
            self._index = 0
            self.clear()
        self._mode = WaveMode.LIVE
        self._recording = recording
        self._timer.start()
        self.update()

    def set_recording(self, recording: bool) -> None:
        """Grey (waiting for the first sound) or red (saving)."""
        if recording != self._recording:
            self._recording = recording
            self.update()

    def stop_following(self) -> None:
        self._timer.stop()
        self._source = None
        self._recording = False
        self._levels = (-math.inf,) * self._channels
        self.update()

    def refresh(self) -> None:
        """One tick of the timer: only the new columns and the levels; then a repaint."""
        source = self._source
        if source is None:
            return
        columns, self._index = source.peaks_since(self._index)
        self.add_columns(columns)
        self.set_levels(source.level_dbfs)

    def add_columns(self, columns: PeakColumns) -> None:
        if columns.shape[0] == 0 or columns.shape[1] != self._channels:
            return
        joined = np.concatenate((self._live, columns.astype(np.float32, copy=False)))
        self._live = joined[-LIVE_COLUMNS:]
        self.update()

    def set_levels(self, levels: Sequence[float]) -> None:
        now = self._clock()
        values = tuple(levels)[: self._channels]
        values += (-math.inf,) * (self._channels - len(values))
        for channel, level in enumerate(values):
            if level >= CLIP_DBFS:
                self._clip_until[channel] = now + defaults.RECORD_CLIP_HOLD_S
        self._levels = values
        self.update()

    def show_overview(
        self, columns: PeakColumns, trimmed_start_s: float, trimmed_end_s: float, total_s: float
    ) -> None:
        """The whole recording (Recorder.overview(wave_width())), with the trimmed silence shaded."""
        self._timer.stop()
        self._source = None
        self._recording = False
        self._mode = WaveMode.OVERVIEW
        self._overview = columns
        if total_s > 0:
            start = min(1.0, max(0.0, trimmed_start_s / total_s))
            end = min(1.0 - start, max(0.0, trimmed_end_s / total_s))
        else:
            start = end = 0.0
        self._trimmed = (start, end)
        self._levels = (-math.inf,) * self._channels
        self.update()

    # --- Painting ---------------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt)
        started = time.perf_counter()
        del event
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()
        self.last_paint_s = time.perf_counter() - started

    def _paint(self, painter: QPainter) -> None:
        if self._mode is WaveMode.OVERVIEW:
            columns, slots = self._overview, max(1, self._overview.shape[0])
        else:
            columns, slots = self._live, LIVE_COLUMNS
        labels = (self.tr("E"), self.tr("D")) if self._channels == 2 else (self.tr("M"),)
        pen = QPen(self.wave_color())
        pen.setWidthF(max(1.0, self.lane_rect(0).width() / slots))
        now = self._clock()
        for channel in range(self._channels):
            rect = self.lane_rect(channel)
            painter.fillRect(rect, LANE_BACKGROUND)
            painter.setPen(CENTRE_LINE)
            painter.drawLine(QLineF(rect.left(), rect.center().y(), rect.right(), rect.center().y()))
            painter.setPen(pen)
            if columns.shape[1] == self._channels:
                painter.drawLines(column_lines(columns, channel, rect, slots))
            for shade in self.shaded_rects(channel):
                painter.fillRect(shade, TRIMMED_SHADE)
            painter.setPen(TEXT_COLOR)
            painter.drawText(
                QRectF(MARGIN, rect.top(), LANE_LABEL_WIDTH, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                labels[channel],
            )
            self._paint_meter(painter, rect, channel, now)

    def _paint_meter(self, painter: QPainter, lane: QRectF, channel: int, now: float) -> None:
        level = self._levels[channel] if channel < len(self._levels) else -math.inf
        text_rect = QRectF(lane.right() + LANE_GAP, lane.top(), METER_TEXT_WIDTH, lane.height())
        painter.setPen(TEXT_COLOR)
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, level_text(level)
        )
        bar = QRectF(text_rect.right() + LANE_GAP, lane.center().y() - 6, METER_WIDTH, 12)
        painter.fillRect(bar, METER_BACKGROUND)
        fill = meter_fraction(level)
        if fill > 0:
            color = METER_HOT_COLOR if level >= METER_HOT_DBFS else METER_COLOR
            painter.fillRect(QRectF(bar.left(), bar.top(), bar.width() * fill, bar.height()), color)
        clip = QRectF(bar.right() + LANE_GAP, bar.top(), CLIP_MARK_WIDTH, bar.height())
        painter.fillRect(clip, CLIP_ON_COLOR if now < self._clip_until[channel] else CLIP_OFF_COLOR)

    @staticmethod
    def _height_for(channels: int) -> int:
        return 2 * MARGIN + channels * LANE_HEIGHT + (channels - 1) * LANE_GAP
