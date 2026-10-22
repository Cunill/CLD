"""A thousand photos: the view is built in under a second and the window never freezes (§1.2).

The latency probe is a timer that should fire every few milliseconds: the longest gap between
two shots is how long the GUI thread was busy, which rule 6 caps at 50 ms for the core work and
the acceptance criterion of B10 caps at 100 ms for the window.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with

pytestmark = [pytest.mark.ui, pytest.mark.lent]

PHOTOS = 1000
BUILD_LIMIT_S = 1.0
LATENCY_LIMIT_S = 0.100
PROBE_INTERVAL_MS = 5


class LatencyProbe(QObject):
    """Records the gap between two shots of a fast timer (how long the GUI thread was busy)."""

    def __init__(self, interval_ms: int = PROBE_INTERVAL_MS) -> None:
        super().__init__()
        self.gaps: list[float] = []
        self._last = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._last = time.perf_counter()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        now = time.perf_counter()
        self.gaps.append(now - self._last)
        self._last = now

    @property
    def worst(self) -> float:
        return max(self.gaps) if self.gaps else 0.0


def test_the_view_of_a_thousand_photos_is_built_in_under_a_second(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> None:
    controller = controller_with(PHOTOS)
    started = time.perf_counter()
    window = build_window(qtbot, controller, thumbnails, questions)
    QApplication.processEvents()
    elapsed = time.perf_counter() - started
    assert window.view.model().rowCount() == PHOTOS
    assert elapsed < BUILD_LIMIT_S, f"la vista ha trigat {elapsed:.2f} s"
    window.close()


def test_only_the_visible_thumbnails_are_asked_for(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> None:
    window = build_window(qtbot, controller_with(PHOTOS), thumbnails, questions)
    window.view.request_visible_thumbnails()
    QApplication.processEvents()
    asked = len(set(thumbnails.requested))
    assert 0 < asked < PHOTOS / 4, f"s'han demanat {asked} miniatures de {PHOTOS}"
    window.close()


def test_the_window_never_freezes_while_the_thumbnails_arrive(
    qtbot: QtBot, questions: RecordedQuestions
) -> None:
    service = FakeThumbnailService(delay_s=0.002)
    window = build_window(qtbot, controller_with(PHOTOS), service, questions)
    probe = LatencyProbe()
    probe.start()
    bar = window.view.verticalScrollBar()
    steps = 12
    for step in range(1, steps + 1):
        bar.setValue(round(bar.maximum() * step / steps))
        qtbot.wait(60)
    qtbot.wait(200)
    probe.stop()
    window.close()
    service.close()
    assert probe.gaps, "la sonda no ha arrencat"
    assert probe.worst < LATENCY_LIMIT_S, f"la finestra s'ha bloquejat {probe.worst * 1000:.0f} ms"
    assert len(set(service.requested)) > 20, "cap miniatura s'ha demanat mentre es desplaçava"


def test_the_thumbnails_in_memory_are_bounded(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> None:
    """A thousand 256 px thumbnails would be hundreds of megabytes: the oldest ones are dropped."""
    from passimaker.ui.thumbnails import MAX_CACHED

    window = build_window(qtbot, controller_with(PHOTOS), thumbnails, questions)
    window.thumbnails.request(window.model.photos())
    thumbnails.wait()
    qtbot.waitUntil(lambda: window.thumbnails.cached_count >= MAX_CACHED, timeout=60_000)
    qtbot.wait(200)
    assert window.thumbnails.cached_count <= MAX_CACHED
    window.close()
