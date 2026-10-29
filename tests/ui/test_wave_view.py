"""C10: the waves of "Grava el que sona" (ESPECIFICACIO §1.7 ter "Ones", annex PLA_GRAVACIO §2.4).

Lanes per channel, colours (grey before recording, red while recording), the overview with the
trimmed silence shaded, the level meter and its clipping mark, and the cost of a repaint. No test
opens a sound card: the view follows a fake source or the fake capture backend.
"""

from __future__ import annotations

import math
import statistics

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from passimaker.model import defaults
from passimaker.recorder import Monitor, PeakColumns
from passimaker.ui.wave_view import (
    IDLE_COLOR,
    LIVE_COLUMNS,
    OVERVIEW_COLOR,
    RECORDING_COLOR,
    WaveMode,
    WaveView,
    level_text,
    meter_fraction,
)
from tests.fakes.recorder import MICROPHONE, SPEAKERS, FakeCaptureBackend, Tone

pytestmark = pytest.mark.ui

REPAINT_LIMIT_S = 0.005
"""PLA_YOUTUBE, fitxa del C10: a repaint of the waves takes less than 5 ms."""


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class ScriptedSource:
    """Hands out `per_tick` new columns each time and records the indices it was asked for."""

    def __init__(self, channels: int = 2, per_tick: int = 2, amplitude: float = 0.5) -> None:
        self.channels = channels
        self.per_tick = per_tick
        self.amplitude = amplitude
        self.total = 0
        self.asked: list[int] = []
        self.level_dbfs: tuple[float, ...] = (-6.0,) * channels

    def peaks_since(self, index: int) -> tuple[PeakColumns, int]:
        self.asked.append(index)
        self.total += self.per_tick
        count = self.total - index
        columns = np.empty((count, self.channels, 2), dtype=np.float32)
        columns[:, :, 0] = -self.amplitude
        columns[:, :, 1] = self.amplitude
        return columns, self.total


def columns(count: int, channels: int = 2, amplitude: float = 0.5) -> PeakColumns:
    data = np.empty((count, channels, 2), dtype=np.float32)
    data[:, :, 0] = -amplitude
    data[:, :, 1] = amplitude
    return data


def make_view(qtbot: QtBot, clock: FakeClock | None = None) -> WaveView:
    view = WaveView(clock=clock or FakeClock())
    view.resize(700, view.height())
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)
    return view


def pixel(view: WaveView, x: float, y: float) -> QColor:
    return view.grab().toImage().pixelColor(round(x), round(y))


# --- Lanes and colours ------------------------------------------------------------------------------


def test_one_lane_per_channel_and_one_for_a_mono_source(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert view.channels == 2
    two = view.height()
    assert view.lane_rect(1).top() > view.lane_rect(0).bottom()
    view.set_channels(MICROPHONE.recorded_channels)
    assert view.channels == 1
    assert view.height() < two
    view.set_channels(6)  # a 5.1 source is recorded as its stereo mix
    assert view.channels == 2


def test_grey_before_recording_red_while_recording(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    source = ScriptedSource(amplitude=0.9)
    view.follow(source)
    view.refresh()
    assert view.wave_color() == IDLE_COLOR
    lane = view.lane_rect(0)
    right = lane.right() - 1
    assert pixel(view, right, lane.center().y() - 5) == IDLE_COLOR
    view.set_recording(True)
    assert view.wave_color() == RECORDING_COLOR
    assert pixel(view, right, lane.center().y() - 5) == RECORDING_COLOR
    view.set_recording(False)  # "Comença quan soni" still waiting: grey
    assert view.wave_color() == IDLE_COLOR


def test_the_live_wave_keeps_the_last_ten_seconds_and_grows_from_the_right(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    assert LIVE_COLUMNS == defaults.RECORD_WAVE_WINDOW_S * defaults.RECORD_PEAK_COLUMNS_PER_S
    view.add_columns(columns(10, amplitude=0.9))
    lane = view.lane_rect(0)
    assert pixel(view, lane.right() - 1, lane.center().y() - 10) == IDLE_COLOR
    assert pixel(view, lane.left() + 2, lane.center().y() - 10) != IDLE_COLOR
    view.add_columns(columns(LIVE_COLUMNS + 50))
    assert view.live_columns.shape[0] == LIVE_COLUMNS


def test_the_timer_collects_only_the_new_columns(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    source = ScriptedSource(per_tick=3)
    view.follow(source)
    qtbot.waitUntil(lambda: len(source.asked) >= 4, timeout=2_000)
    assert source.asked[:4] == [0, 3, 6, 9]
    assert view.live_columns.shape[0] == source.total
    view.stop_following()
    asked = len(source.asked)
    qtbot.wait(100)
    assert len(source.asked) == asked


def test_following_a_monitor_of_the_fake_backend(qtbot: QtBot) -> None:
    backend = FakeCaptureBackend(script=[Tone(1.0, amplitude=0.5)])
    monitor = Monitor(SPEAKERS, backend=backend)
    monitor.start()
    try:
        view = make_view(qtbot)
        view.follow(monitor)
        qtbot.waitUntil(lambda: view.live_columns.shape[0] == 50, timeout=2_000)
        assert view.levels[0] == pytest.approx(20 * math.log10(0.5), abs=0.1)
    finally:
        monitor.stop()


# --- Overview --------------------------------------------------------------------------------------


def test_the_overview_shades_the_trimmed_silence(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    width = view.wave_width()
    whole = columns(width, amplitude=0.8)
    view.show_overview(whole, trimmed_start_s=1.0, trimmed_end_s=2.0, total_s=10.0)
    assert view.mode is WaveMode.OVERVIEW
    assert view.wave_color() == OVERVIEW_COLOR
    assert view.trimmed_fractions == (pytest.approx(0.1), pytest.approx(0.2))
    lane = view.lane_rect(0)
    start, end = view.shaded_rects(0)
    assert start.left() == lane.left()
    assert start.width() == pytest.approx(lane.width() * 0.1)
    assert end.right() == pytest.approx(lane.right())
    assert end.width() == pytest.approx(lane.width() * 0.2)
    assert len(view.shaded_rects(1)) == 2
    y = lane.center().y() - 10
    kept = pixel(view, lane.left() + lane.width() * 0.5, y)
    shaded = pixel(view, lane.left() + lane.width() * 0.05, y)
    assert kept == OVERVIEW_COLOR
    assert shaded.lightness() < kept.lightness()


def test_nothing_trimmed_nothing_shaded(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    view.show_overview(columns(view.wave_width()), 0.0, 0.0, 5.0)
    assert view.shaded_rects() == []
    view.clear()
    assert view.mode is WaveMode.LIVE


# --- Level meter and clipping ----------------------------------------------------------------------


def test_meter_scale_and_text() -> None:
    assert meter_fraction(0.0) == 1.0
    assert meter_fraction(-30.0) == pytest.approx(0.5)
    assert meter_fraction(-math.inf) == 0.0
    assert meter_fraction(-90.0) == 0.0
    assert level_text(-6.2) == "-6 dB"
    assert level_text(0.0) == "0 dB"
    assert level_text(-0.3) == "0 dB"
    assert level_text(-math.inf) == "– dB"


def test_the_clipping_mark_stays_lit_for_two_seconds(qtbot: QtBot) -> None:
    clock = FakeClock()
    view = make_view(qtbot, clock)
    view.set_levels((-3.0, 0.0))
    assert not view.clipping(0)
    assert view.clipping(1)
    clock.now += defaults.RECORD_CLIP_HOLD_S - 0.1
    view.set_levels((-3.0, -20.0))
    assert view.clipping(1)
    clock.now += 0.2
    assert not view.clipping(1)


# --- Not clickable ---------------------------------------------------------------------------------


def test_the_waves_do_nothing_on_click(qtbot: QtBot) -> None:
    view = make_view(qtbot)
    view.add_columns(columns(100))
    before = view.live_columns.copy()
    lane = view.lane_rect(0)
    centre = QPoint(round(lane.center().x()), round(lane.center().y()))
    qtbot.mouseClick(view, Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseDClick(view, Qt.MouseButton.LeftButton, pos=centre)
    assert np.array_equal(view.live_columns, before)
    assert view.mode is WaveMode.LIVE
    assert view.focusPolicy() is Qt.FocusPolicy.NoFocus


# --- Performance -----------------------------------------------------------------------------------


@pytest.mark.parametrize("channels", [1, 2])
def test_a_repaint_takes_under_five_milliseconds(qtbot: QtBot, channels: int) -> None:
    view = make_view(qtbot)
    view.resize(1200, view.height())
    view.set_channels(channels)
    source = ScriptedSource(channels=channels, per_tick=round(defaults.RECORD_PEAK_COLUMNS_PER_S / 30) + 1)
    view.follow(source, recording=True)
    view.add_columns(columns(LIVE_COLUMNS, channels, 0.7))
    times: list[float] = []
    for _ in range(40):
        view.refresh()
        view.repaint()
        QApplication.processEvents()
        times.append(view.last_paint_s)
    view.stop_following()
    assert view.live_columns.shape[0] == LIVE_COLUMNS
    assert statistics.median(times) < REPAINT_LIMIT_S
