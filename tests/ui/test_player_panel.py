"""B13 · The preview panel in the window: frames, controls, keys and the time criteria of the plan.

The window tests use the real compositor with synthetic images and the internal clock (no
music). The tests that need the sound build the panel alone with a simulated sound device.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from pytestqt.qtbot import QtBot

from passimaker.audio import AudioSource
from passimaker.common import RGBImage
from passimaker.model import OutputFormat, Photo, Project, ProjectController
from passimaker.model.commands import AddSongs, MovePhotos, SetDefaultDuration, SetPhotoMotion
from passimaker.model.types import MotionType, Song
from passimaker.preview import photo_start
from passimaker.ui.main_window import MainWindow
from passimaker.ui.player_panel import PlayerPanel
from tests.fakes.audio import ToneAudioSource
from tests.ui.helpers import FakeThumbnailService, controller_with, images
from tests.unit.preview.fakes import FakeAudioOutput, SimulatedClockFactory

pytestmark = pytest.mark.ui

TIMEOUT_MS = 20_000


def wait_frame(qtbot: QtBot, panel: PlayerPanel) -> QImage:
    panel.wait(TIMEOUT_MS)
    qtbot.waitUntil(lambda: panel.frame is not None, timeout=TIMEOUT_MS)
    qtbot.wait(20)  # the last queued frame
    frame = panel.frame
    assert frame is not None
    return frame


def time_to_next_frame(qtbot: QtBot, panel: PlayerPanel, action: object) -> float:
    """Seconds from `action()` to the next frame on screen."""
    with qtbot.waitSignal(panel.player.frame_ready, timeout=TIMEOUT_MS):
        start = time.perf_counter()
        action()  # type: ignore[operator]
    return time.perf_counter() - start


class CachedIntermediates:
    """The intermediates of the fake service, kept in memory (as on disk after the first time)."""

    def __init__(self, service: FakeThumbnailService) -> None:
        self._service = service
        self._cache: dict[str, RGBImage] = {}

    def __call__(self, photo: Photo) -> RGBImage:
        image = self._cache.get(photo.id)
        if image is None:
            image = self._cache[photo.id] = self._service.get_intermediate(photo)
        return image


@pytest.fixture
def standalone(qtbot: QtBot) -> Iterator[tuple[PlayerPanel, ProjectController, FakeAudioOutput]]:
    """A panel alone, with a simulated sound device and music that is a pure tone."""
    controller = controller_with(6)
    output = FakeAudioOutput()
    prepared: list[Project] = []

    def preparer(project: Project) -> AudioSource | None:
        prepared.append(project)
        return ToneAudioSource(60.0) if project.music.songs else None

    panel = PlayerPanel(
        controller,
        images(),
        output=output,
        audio_preparer=preparer,
        clock_factory=SimulatedClockFactory(output.clock),
    )
    panel.resize(640, 420)
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    yield panel, controller, output
    panel.close_panel()


# --- What it shows -------------------------------------------------------------------------------


def test_selecting_a_photo_shows_it(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.select_ids(["p0003"])
    frame = wait_frame(qtbot, window.player_panel)
    assert frame.width() > 0 and frame.height() > 0
    # The frame keeps the proportion of the chosen format (§1.11).
    width, height = OutputFormat.HORIZONTAL.size
    assert frame.width() / frame.height() == pytest.approx(width / height, rel=0.02)
    # It is the start of the photo, where it is fully visible (§1.8).
    timeline = window.player_panel.player.timeline
    assert window.player_panel.player.position == pytest.approx(photo_start(timeline, 2), abs=1 / 30)
    assert window.player_panel.player.photo_index == 2


def test_the_vertical_format_changes_the_shape(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.select_ids(["p0002"])
    wait_frame(qtbot, window.player_panel)
    window.format_action.setChecked(True)
    panel = window.player_panel
    panel.wait(TIMEOUT_MS)
    qtbot.waitUntil(
        lambda: panel.frame is not None and panel.frame.height() > panel.frame.width(), timeout=TIMEOUT_MS
    )
    frame = panel.frame
    assert frame is not None
    width, height = OutputFormat.VERTICAL.size
    assert frame.width() / frame.height() == pytest.approx(width / height, rel=0.02)
    assert max(frame.width(), frame.height()) <= 960


def test_an_empty_project_shows_black_and_does_not_play(qtbot: QtBot, window: MainWindow) -> None:
    panel = window.player_panel
    frame = wait_frame(qtbot, panel)
    assert frame.pixelColor(frame.width() // 2, frame.height() // 2).value() == 0
    panel.toggle_play()
    panel.wait(TIMEOUT_MS)
    assert not panel.player.playing
    assert panel.time_label.text() == "0:00 / 0:00"


def test_the_preview_is_never_larger_than_960_by_540(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.resize(2400, 1500)
    window.splitter.setSizes([2000, 400])
    frame = wait_frame(qtbot, window.player_panel)
    assert (frame.width(), frame.height()) == (960, 540)


# --- Controls ------------------------------------------------------------------------------------


def test_play_and_pause_with_the_button(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    panel = window_with_photos.player_panel
    wait_frame(qtbot, panel)
    with qtbot.waitSignal(panel.player.state_changed, timeout=TIMEOUT_MS):
        qtbot.mouseClick(panel.play_button, Qt.MouseButton.LeftButton)
    assert panel.player.playing
    assert panel.play_button.toolTip() == "Pausa (espai)"
    qtbot.wait(400)  # real time: the internal clock
    qtbot.mouseClick(panel.play_button, Qt.MouseButton.LeftButton)
    panel.wait(TIMEOUT_MS)
    qtbot.wait(20)
    assert not panel.player.playing
    assert panel.play_button.toolTip() == "Reprodueix (espai)"
    assert 0.2 < panel.player.position < 3.0


def test_previous_and_next_photo(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    panel = window_with_photos.player_panel
    wait_frame(qtbot, panel)
    timeline = panel.player.timeline
    for expected in (1, 2, 3):
        qtbot.mouseClick(panel.next_button, Qt.MouseButton.LeftButton)
        wait_frame(qtbot, panel)
        assert panel.player.photo_index == expected
        assert panel.player.position == pytest.approx(photo_start(timeline, expected), abs=1 / 30)
    qtbot.mouseClick(panel.previous_button, Qt.MouseButton.LeftButton)
    wait_frame(qtbot, panel)
    assert panel.player.photo_index == 2
    for _ in range(5):
        qtbot.mouseClick(panel.previous_button, Qt.MouseButton.LeftButton)
    wait_frame(qtbot, panel)
    assert panel.player.photo_index == 0


def test_clicking_the_time_bar_jumps_there(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    panel = window_with_photos.player_panel
    wait_frame(qtbot, panel)
    bar = panel.time_bar
    total = panel.player.timeline.total_duration_s
    qtbot.mouseClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(bar.width() * 3 // 4, bar.height() // 2))
    wait_frame(qtbot, panel)
    assert panel.player.position == pytest.approx(0.75 * total, abs=0.08 * total)
    assert panel.time_label.text().endswith(" / 0:" + f"{round(total):02d}")


def test_the_label_shows_current_and_total_time(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    panel = window_with_photos.player_panel
    window_with_photos.view.select_ids(["p0006"])
    wait_frame(qtbot, panel)
    position = panel.player.position
    total = panel.player.timeline.total_duration_s
    assert panel.time_label.text() == f"0:{round(position):02d} / 0:{round(total):02d}"


# --- Keys ----------------------------------------------------------------------------------------


def test_space_plays_and_pauses_from_the_storyboard(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.player_panel
    wait_frame(qtbot, panel)
    window.view.setFocus()
    qtbot.keyClick(window.view, Qt.Key.Key_Space)
    assert panel.player.playing
    qtbot.keyClick(window.view, Qt.Key.Key_Space)
    assert not panel.player.playing


def test_space_in_a_number_box_is_typing(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.player_panel
    wait_frame(qtbot, panel)
    box = window.panel.duration
    box.setFocus()
    qtbot.keyClick(box, Qt.Key.Key_Space)
    assert not panel.player.playing


def test_arrows_go_to_the_previous_and_next_photo_in_the_preview(
    qtbot: QtBot, window_with_photos: MainWindow
) -> None:
    panel = window_with_photos.player_panel
    wait_frame(qtbot, panel)
    qtbot.mouseClick(panel.view, Qt.MouseButton.LeftButton)
    assert panel.view.hasFocus()
    qtbot.keyClick(panel.view, Qt.Key.Key_Right)
    qtbot.keyClick(panel.view, Qt.Key.Key_Right)
    wait_frame(qtbot, panel)
    assert panel.player.photo_index == 2
    qtbot.keyClick(panel.view, Qt.Key.Key_Left)
    wait_frame(qtbot, panel)
    assert panel.player.photo_index == 1


def test_arrows_in_the_storyboard_move_the_selection_and_the_preview_follows(
    qtbot: QtBot, window_with_photos: MainWindow
) -> None:
    window = window_with_photos
    panel = window.player_panel
    window.view.select_ids(["p0004"])
    wait_frame(qtbot, panel)
    window.view.setFocus()
    qtbot.keyClick(window.view, Qt.Key.Key_Right)
    assert window.view.selected_ids() == ("p0005",)
    wait_frame(qtbot, panel)
    assert panel.player.photo_index == 4
    # Ctrl+→ still moves the photo (B10): the order changes, the preview is not a second target.
    qtbot.keyClick(window.view, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert [p.id for p in window.controller.project.photos][5] == "p0005"


# --- Time criteria of the plan -------------------------------------------------------------------


def test_in_pause_a_change_of_duration_or_motion_is_seen_within_200_ms(
    qtbot: QtBot, window_with_photos: MainWindow
) -> None:
    window = window_with_photos
    panel = window.player_panel
    window.view.select_ids(["p0003"])
    wait_frame(qtbot, panel)
    controller = window.controller
    times = [
        time_to_next_frame(qtbot, panel, lambda: controller.execute(SetDefaultDuration(2.5))),
        time_to_next_frame(
            qtbot, panel, lambda: controller.execute(SetPhotoMotion(frozenset({"p0003"}), MotionType.ZOOM_IN))
        ),
        time_to_next_frame(qtbot, panel, lambda: controller.execute(SetDefaultDuration(1.5))),
    ]
    assert max(times) < 0.200, times
    assert panel.player.timeline.slots[0].slot_end == pytest.approx(1.5)


def test_in_pause_the_preview_stays_on_its_photo_after_an_edit(
    qtbot: QtBot, window_with_photos: MainWindow
) -> None:
    window = window_with_photos
    panel = window.player_panel
    window.view.select_ids(["p0002"])
    wait_frame(qtbot, panel)
    before = panel.frame
    time_to_next_frame(qtbot, panel, lambda: window.controller.execute(MovePhotos(("p0002",), 6)))
    assert panel.frame is not before
    timeline = panel.player.timeline
    assert timeline.slots[5].photo_id == "p0002"
    assert panel.player.position == pytest.approx(photo_start(timeline, 5), abs=1 / 30)


@pytest.mark.lent
def test_going_to_a_photo_of_1000_takes_less_than_300_ms(qtbot: QtBot) -> None:
    service = FakeThumbnailService()
    controller = controller_with(1000)
    intermediates = CachedIntermediates(service)
    targets = [10, 250, 500, 749, 998]
    for index in targets:
        intermediates(controller.project.photos[index])
    panel = PlayerPanel(controller, images(), intermediates)
    panel.resize(980, 600)
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    wait_frame(qtbot, panel)
    try:
        times = [
            time_to_next_frame(qtbot, panel, lambda i=i: panel.show_photo(controller.project.photos[i].id))
            for i in targets
        ]
        assert max(times) < 0.300, times
        # And playing starts from any point in less than half a second (§1.8).
        panel.player.seek_photo(600)
        panel.wait(TIMEOUT_MS)
        start = time.perf_counter()
        with qtbot.waitSignal(panel.player.frame_ready, timeout=TIMEOUT_MS):
            panel.toggle_play()
        assert time.perf_counter() - start < 0.5
    finally:
        panel.close_panel()
        service.close()


# --- Music ---------------------------------------------------------------------------------------


def song(index: int) -> Song:
    return Song(f"s{index}", Path(f"/musica/{index}.mp3"), None, 120.0)


def test_with_music_the_sound_device_is_the_clock(
    qtbot: QtBot, standalone: tuple[PlayerPanel, ProjectController, FakeAudioOutput]
) -> None:
    panel, controller, output = standalone
    wait_frame(qtbot, panel)
    assert panel.audio is None
    controller.execute(AddSongs((song(1),)))
    qtbot.waitUntil(lambda: panel.audio is not None, timeout=TIMEOUT_MS)
    panel.toggle_play()
    qtbot.waitUntil(lambda: output.playing, timeout=TIMEOUT_MS)
    assert output.starts == [0.0]
    output.clock.advance(1.0)
    qtbot.waitUntil(lambda: panel.player.position >= 1.0, timeout=TIMEOUT_MS)
    panel.toggle_play()
    panel.wait(TIMEOUT_MS)
    assert not output.playing
    # In pause the exact frame of the clock is drawn (the playing ones may aim a little ahead).
    qtbot.waitUntil(lambda: abs(panel.player.position - 1.0) < 1 / 30, timeout=TIMEOUT_MS)


def test_a_change_of_music_replaces_the_sound_while_playing(
    qtbot: QtBot, standalone: tuple[PlayerPanel, ProjectController, FakeAudioOutput]
) -> None:
    panel, controller, output = standalone
    controller.execute(AddSongs((song(1),)))
    qtbot.waitUntil(lambda: panel.audio is not None, timeout=TIMEOUT_MS)
    first = panel.audio
    panel.toggle_play()
    qtbot.waitUntil(lambda: output.playing, timeout=TIMEOUT_MS)
    output.clock.advance(2.0)
    qtbot.waitUntil(lambda: panel.player.position >= 2.0, timeout=TIMEOUT_MS)
    panel.reload_audio()  # what B11 calls when the music changes
    qtbot.waitUntil(lambda: panel.audio is not first and len(output.starts) == 2, timeout=TIMEOUT_MS)
    assert output.starts[1] == pytest.approx(2.0, abs=0.1)
    assert panel.player.playing


def test_selecting_a_photo_while_playing_goes_on_from_there(
    qtbot: QtBot, standalone: tuple[PlayerPanel, ProjectController, FakeAudioOutput]
) -> None:
    panel, controller, output = standalone
    controller.execute(AddSongs((song(1),)))
    qtbot.waitUntil(lambda: panel.audio is not None, timeout=TIMEOUT_MS)
    panel.toggle_play()
    qtbot.waitUntil(lambda: output.playing, timeout=TIMEOUT_MS)
    panel.show_photo(controller.project.photos[4].id)
    target = photo_start(panel.player.timeline, 4)
    qtbot.waitUntil(lambda: output.starts[-1] == target, timeout=TIMEOUT_MS)
    assert panel.player.playing


def test_closing_the_window_stops_the_player(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    panel = window_with_photos.player_panel
    wait_frame(qtbot, panel)
    panel.toggle_play()
    qtbot.wait(100)
    window_with_photos.close()
    assert not panel.player._thread.is_alive()  # pyright: ignore[reportPrivateUsage]
