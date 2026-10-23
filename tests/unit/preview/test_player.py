"""B13 · Player: the loop on its own thread, and the Qt signals on the interface thread."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import numpy as np
import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QImage
from pytestqt.qtbot import QtBot

from passimaker.preview import Player, photo_start, to_qimage
from tests.fakes.audio import ToneAudioSource
from tests.unit.preview.fakes import FakeAudioOutput, SimulatedClockFactory, SlowFrames
from tests.unit.preview.test_loop import timeline_of

TIMEOUT_MS = 10_000


@pytest.fixture
def player(qtbot: QtBot) -> Iterator[tuple[Player, FakeAudioOutput, SlowFrames]]:
    output = FakeAudioOutput()
    frames = SlowFrames(output.clock, (0.0,))
    timeline = timeline_of()
    made = Player(
        frames,
        timeline,
        ToneAudioSource(timeline.total_duration_s),
        output,
        clock_factory=SimulatedClockFactory(output.clock),
        size=(64, 36),
    )
    yield made, output, frames
    made.close()


def test_frames_arrive_on_the_interface_thread(
    qtbot: QtBot, player: tuple[Player, FakeAudioOutput, SlowFrames]
) -> None:
    made, _, _ = player
    threads: list[object] = []
    made.frame_ready.connect(lambda image, t: threads.append(QThread.currentThread()))
    with qtbot.waitSignal(made.frame_ready, timeout=TIMEOUT_MS) as blocker:
        made.refresh()
    assert blocker.args is not None
    image, t = blocker.args
    assert isinstance(image, QImage)
    assert (image.width(), image.height()) == (64, 36)
    assert t == 0.0
    assert threads[-1] is made.thread()


def test_a_seek_drops_the_frames_drawn_before_it(
    qtbot: QtBot, player: tuple[Player, FakeAudioOutput, SlowFrames]
) -> None:
    made, _, _ = player
    made.wait_idle()
    seen: list[float] = []
    made.frame_ready.connect(lambda image, t: seen.append(t))
    made.refresh()
    made.seek_photo(4)  # before the refreshed frame is handed over: it is stale
    target = photo_start(made.timeline, 4)
    assert made.position == target
    qtbot.waitUntil(lambda: bool(seen) and seen[-1] == pytest.approx(target, abs=1 / 30), timeout=TIMEOUT_MS)
    assert all(t == pytest.approx(target, abs=1 / 30) for t in seen[-1:])
    assert made.photo_index == 4


def test_playing_and_pausing_report_the_state(
    qtbot: QtBot, player: tuple[Player, FakeAudioOutput, SlowFrames]
) -> None:
    made, output, _ = player
    with qtbot.waitSignal(made.state_changed, timeout=TIMEOUT_MS) as blocker:
        made.toggle()
    assert blocker.args is not None and blocker.args[0] is True
    assert made.playing and output.playing
    output.clock.advance(5.5)
    with qtbot.waitSignal(made.state_changed, timeout=TIMEOUT_MS) as blocker:
        made.toggle()
    assert blocker.args is not None
    playing, t, index = blocker.args
    assert not playing and t == pytest.approx(5.5) and index == 1


def test_close_stops_the_thread_and_the_sound(qtbot: QtBot) -> None:
    output = FakeAudioOutput()
    timeline = timeline_of()
    made = Player(SlowFrames(output.clock), timeline, ToneAudioSource(10.0), output, size=(32, 18))
    made.play()
    qtbot.waitUntil(lambda: output.playing, timeout=TIMEOUT_MS)
    made.close()
    made.close()
    assert not output.playing
    assert not any(t.name == "passimaker-preview" and t.is_alive() for t in threading.enumerate())


def test_to_qimage_copies_the_pixels() -> None:
    array = np.zeros((2, 3, 3), dtype=np.uint8)
    array[1, 2] = (10, 20, 30)
    array.setflags(write=False)
    image = to_qimage(array)
    colour = image.pixelColor(2, 1)
    assert (colour.red(), colour.green(), colour.blue()) == (10, 20, 30)
