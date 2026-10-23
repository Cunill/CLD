"""Song panel, trim bar and the music settings of "Avançat" (block B14, §1.7).

The songs are real WAV files, so the waveform and [Escoltar el tros] go through FFmpeg and the
mixer as in the program; only the sound device is a fake.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QPoint, Qt
from pytestqt.qtbot import QtBot

from passimaker.audio import SAMPLE_RATE, AudioSource
from passimaker.common import PassiMakerError
from passimaker.model import Fade, Song
from passimaker.model.commands import AddSongs, SetProjectSettings, UpdateSong
from passimaker.preview import Clock, SoundDeviceOutput
from passimaker.ui.main_window import MainWindow
from passimaker.ui.project_panel import CUSTOM_INTENSITY
from passimaker.ui.properties import PropertiesPanel
from passimaker.ui.song_panel import SongListening
from passimaker.ui.trim_bar import TRIM_STEP_S, WAVEFORM_POINTS, WaveformLoader
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with, write_song

pytestmark = pytest.mark.ui

SONG_S = 6.0
TIMEOUT_MS = 10_000


class _StillClock:
    def now(self) -> float:
        return 0.0


class FakeOutput:
    """The sound device: records what it was asked to play."""

    def __init__(self) -> None:
        self.started: list[AudioSource] = []
        self.stops = 0

    def start(self, source: AudioSource, from_s: float) -> Clock:
        self.started.append(source)
        return _StillClock()

    def stop(self) -> None:
        self.stops += 1


@pytest.fixture
def song_file(tmp_path: Path) -> Path:
    return write_song(tmp_path / "música" / "Cançó A.wav", SONG_S)


@pytest.fixture
def window_with_song(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, song_file: Path
) -> Iterator[MainWindow]:
    controller = controller_with(6)
    controller.execute(
        AddSongs((Song(id="s1", path=song_file, relative_path=None, original_duration_s=SONG_S),))
    )
    made = build_window(qtbot, controller, thumbnails, questions)
    yield made
    made.close()


def select_song(window: MainWindow, row: int = 0) -> None:
    view = window.music_strip.view
    view.selectionModel().select(
        window.music_strip.model.index(row, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def song(window: MainWindow) -> Song:
    return window.controller.project.music.songs[0]


def test_selecting_a_song_opens_its_tab(window_with_song: MainWindow) -> None:
    window = window_with_song
    assert not window.properties.isTabEnabled(PropertiesPanel.SONG)
    select_song(window)
    panel = window.song_panel
    assert window.properties.currentIndex() == PropertiesPanel.SONG
    assert "Cançó A.wav" in panel.title.text()
    assert panel.fade_in_enabled.isChecked()
    assert panel.fade_in.text() == "1,0 s"
    assert panel.fade_out.text() == "3,0 s"
    assert panel.volume.value() == pytest.approx(100)
    assert panel.trim_start.value() == 0
    assert panel.trim_end.value() == pytest.approx(SONG_S)


def test_the_fades_change_the_song(window_with_song: MainWindow) -> None:
    window = window_with_song
    select_song(window)
    panel = window.song_panel
    panel.fade_in_enabled.setChecked(False)
    assert not song(window).fade_in.enabled
    assert not panel.fade_in.isEnabled()
    panel.fade_out.setValue(4.5)
    assert song(window).fade_out.seconds == pytest.approx(4.5)
    panel.fade_out.setValue(25)  # out of range: the box stops at 10 s
    assert song(window).fade_out.seconds == pytest.approx(10.0)
    # The selection survives the edits (the strip is not rebuilt for a change of settings).
    assert window.music_strip.view.selected_ids() == ("s1",)


def test_the_volume_has_its_range(window_with_song: MainWindow) -> None:
    window = window_with_song
    select_song(window)
    window.song_panel.volume.setValue(120)
    assert song(window).volume == pytest.approx(1.2)
    window.song_panel.volume.setValue(400)
    assert song(window).volume == pytest.approx(1.5)


def test_the_trim_boxes_and_the_handles_are_in_step(window_with_song: MainWindow) -> None:
    window = window_with_song
    select_song(window)
    panel = window.song_panel
    panel.trim_start.setValue(1.0)
    assert song(window).trim_start_s == pytest.approx(1.0)
    assert panel.trim_bar.start == pytest.approx(1.0)
    panel.trim_end.setValue(4.0)
    assert song(window).trim_end_s == pytest.approx(4.0)
    assert panel.trim_bar.end == pytest.approx(4.0)
    assert "0:03" in window.music_strip.model.index(0, 0).data()  # the strip shows the trimmed length
    # The start can never pass the end, nor the end go before the start.
    panel.trim_start.setValue(5.0)
    assert song(window).trim_start_s == pytest.approx(4.0 - TRIM_STEP_S)
    panel.trim_end.setValue(0.5)
    assert song(window).trim_end_s == pytest.approx(4.0)
    # Back to the end of the file: no trim at the end.
    panel.trim_end.setValue(SONG_S)
    assert song(window).trim_end_s is None


def drag(qtbot: QtBot, window: MainWindow, from_s: float, to_s: float) -> None:
    bar = window.song_panel.trim_bar
    y = bar.height() // 2
    qtbot.mousePress(bar, Qt.MouseButton.LeftButton, pos=QPoint(round(bar.x_of(from_s)), y))
    qtbot.mouseMove(bar, QPoint(round(bar.x_of(to_s)), y))


def test_dragging_a_handle_moves_the_boxes_and_sets_the_trim_on_release(
    qtbot: QtBot, window_with_song: MainWindow
) -> None:
    window = window_with_song
    select_song(window)
    panel = window.song_panel
    bar = panel.trim_bar
    bar.resize(600, bar.height())
    drag(qtbot, window, 0.0, 2.0)
    assert bar.dragging
    assert panel.trim_start.value() == pytest.approx(2.0, abs=TRIM_STEP_S)
    assert song(window).trim_start_s == 0  # nothing is sent until the handle is released
    history = window.controller.can_undo
    qtbot.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(round(bar.x_of(2.0)), bar.height() // 2))
    assert song(window).trim_start_s == pytest.approx(2.0, abs=TRIM_STEP_S)
    assert history and window.controller.can_undo
    # The end handle cannot be dragged before the start.
    drag(qtbot, window, SONG_S, 0.5)
    qtbot.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(round(bar.x_of(0.5)), bar.height() // 2))
    edited = song(window)
    assert edited.trim_end_s is not None
    assert edited.trim_end_s == pytest.approx(edited.trim_start_s + TRIM_STEP_S)
    assert panel.trim_end.value() == pytest.approx(edited.trim_end_s)
    # One drag is one step of undo.
    window.undo()
    assert song(window).trim_end_s is None
    assert panel.trim_bar.end == pytest.approx(SONG_S)


def test_the_waveform_is_drawn(qtbot: QtBot, window_with_song: MainWindow) -> None:
    window = window_with_song
    select_song(window)
    bar = window.song_panel.trim_bar
    qtbot.waitUntil(lambda: bar.peaks is not None, timeout=TIMEOUT_MS)
    peaks = bar.peaks
    assert peaks is not None
    assert peaks.size == WAVEFORM_POINTS
    assert 0.15 < float(peaks.max()) < 0.25  # the tone of the file has an amplitude of 0.2


def test_an_unreadable_song_is_explained_in_red(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    broken = tmp_path / "trencada.mp3"
    broken.write_bytes(b"not a song" * 100)
    controller = controller_with(2)
    controller.execute(AddSongs((Song(id="s1", path=broken, relative_path=None, original_duration_s=30.0),)))
    window = build_window(qtbot, controller, thumbnails, questions)
    select_song(window)
    problem = window.song_panel.problem
    qtbot.waitUntil(lambda: bool(problem.text()), timeout=TIMEOUT_MS)
    assert problem.text().startswith("No es pot llegir aquesta cançó:")
    window.close()


def test_listening_plays_only_the_trimmed_part(qtbot: QtBot, window_with_song: MainWindow) -> None:
    window = window_with_song
    output = FakeOutput()
    panel = window.song_panel
    panel.listening.output_factory = lambda: output
    select_song(window)
    panel.trim_start.setValue(1.0)
    panel.trim_end.setValue(3.5)
    with qtbot.waitSignal(panel.listening.started, timeout=TIMEOUT_MS):
        panel.listen.click()
    assert panel.listen.text() == "■ Aturar"
    assert not window.player_panel.player.playing  # the preview is paused meanwhile
    source = output.started[-1]
    assert source.duration_s == pytest.approx(2.5)
    # The fades of the song are in: it starts in silence and sounds in the middle.
    assert abs(source.read(0.0, 16)).max() < 1e-3
    assert abs(source.read(1.2, 4800)).max() > 0.05
    assert abs(source.read(2.5, 16)).max() == 0  # nothing after the chosen part
    panel.listen.click()
    assert panel.listen.text() == "▶ Escoltar el tros"
    panel.listening.wait()
    assert output.stops >= 1


def test_the_preview_starting_stops_the_listening(qtbot: QtBot, window_with_song: MainWindow) -> None:
    window = window_with_song
    panel = window.song_panel
    panel.listening.output_factory = FakeOutput
    select_song(window)
    with qtbot.waitSignal(panel.listening.started, timeout=TIMEOUT_MS):
        panel.listen.click()
    window._on_player_state(False, 0.0, 0)  # a late report of the pause: nothing changes
    assert panel.listening.song_id == "s1"
    with qtbot.waitSignal(panel.listening.stopped, timeout=TIMEOUT_MS):
        window._on_player_state(True, 0.0, 0)  # ▶ in the preview
    assert panel.listen.text() == "▶ Escoltar el tros"


def test_listening_stops_by_itself_at_the_end(qtbot: QtBot, window_with_song: MainWindow) -> None:
    window = window_with_song
    output = FakeOutput()
    panel = window.song_panel
    panel.listening.output_factory = lambda: output
    select_song(window)
    panel.trim_end.setValue(0.5)
    with qtbot.waitSignal(panel.listening.stopped, timeout=TIMEOUT_MS):
        panel.listen.click()
    assert output.started[-1].duration_s * SAMPLE_RATE == pytest.approx(0.5 * SAMPLE_RATE)
    assert panel.listen.text() == "▶ Escoltar el tros"


def test_a_song_edit_prepares_the_music_of_the_preview_again(
    qtbot: QtBot, window_with_song: MainWindow
) -> None:
    window = window_with_song
    preview = window.player_panel
    qtbot.waitUntil(lambda: preview.audio is not None, timeout=TIMEOUT_MS)
    before = preview.audio
    select_song(window)
    window.song_panel.volume.setValue(50)
    qtbot.waitUntil(lambda: preview.audio is not before, timeout=TIMEOUT_MS)


def test_the_advanced_music_settings(window_with_song: MainWindow) -> None:
    window = window_with_song
    panel = window.panel
    panel.advanced.setChecked(True)
    assert panel.master_volume.isVisible()
    panel.master_volume.setValue(80)
    assert window.controller.project.music.master_volume == pytest.approx(0.8)
    panel.master_volume.setValue(130)  # the master volume goes up to 100 %
    assert window.controller.project.music.master_volume == pytest.approx(1.0)
    panel.normalize.setChecked(False)
    assert window.controller.project.music.normalize is False
    panel.fade_to_black.setValue(4.0)
    assert window.controller.project.fade_to_black_s == pytest.approx(4.0)


def test_custom_motion_amounts_show_personalitzada(window_with_song: MainWindow) -> None:
    window = window_with_song
    window.controller.execute(SetProjectSettings(zoom_amount=0.15))
    assert window.panel.intensity.currentIndex() == CUSTOM_INTENSITY
    assert window.panel.intensity.currentText() == "Personalitzada"
    window.panel.intensity.setCurrentIndex(1)
    assert window.controller.project.zoom_amount == pytest.approx(0.09)


def test_removing_the_song_takes_its_tab_away(window_with_song: MainWindow) -> None:
    window = window_with_song
    select_song(window)
    window.music_strip.remove_selected()
    assert not window.properties.isTabEnabled(PropertiesPanel.SONG)
    assert window.properties.currentIndex() == PropertiesPanel.PROJECT


# --- Review of the B14 (fixes) ---------------------------------------------------------------------


def _source(seconds: float = 1.0) -> AudioSource:
    from tests.fakes.audio import ToneAudioSource

    return ToneAudioSource(seconds)


def test_stopping_while_the_part_is_being_prepared_plays_nothing(qtbot: QtBot) -> None:
    """The first listen can take seconds (decoding, loudness): a stop meanwhile must win."""
    release = threading.Event()
    output = FakeOutput()

    def slow_source(_project: object, _song: object) -> AudioSource:
        release.wait(5.0)
        return _source()

    listening = SongListening(output_factory=lambda: output, source_factory=slow_source)
    any_song = Song(id="s1", path=Path("x.wav"), relative_path=None, original_duration_s=1.0)
    listening.play(controller_with(1).project, any_song)
    listening.stop()
    release.set()
    listening.wait()
    assert output.started == []  # it was not even started
    assert listening.song_id is None
    listening.close()


def test_a_missing_sound_device_is_explained(qtbot: QtBot) -> None:
    def no_device() -> FakeOutput:
        raise OSError("PortAudio library not found")

    listening = SongListening(output_factory=no_device, source_factory=lambda _p, _s: _source())
    any_song = Song(id="s1", path=Path("x.wav"), relative_path=None, original_duration_s=1.0)
    with qtbot.waitSignal(listening.failed, timeout=TIMEOUT_MS) as failed:
        listening.play(controller_with(1).project, any_song)
    assert failed.args == ["no s'ha pogut obrir el dispositiu de so."]
    assert listening.song_id is None
    listening.close()


def test_closing_the_listening_closes_the_sound_device(qtbot: QtBot) -> None:
    from tests.unit.preview.test_sound import Streams

    streams = Streams()
    listening = SongListening(
        output_factory=lambda: SoundDeviceOutput(streams), source_factory=lambda _p, _s: _source()
    )
    any_song = Song(id="s1", path=Path("x.wav"), relative_path=None, original_duration_s=1.0)
    with qtbot.waitSignal(listening.started, timeout=TIMEOUT_MS):
        listening.play(controller_with(1).project, any_song)
    listening.stop()  # the end of the part: since M04 the stream stays open for a while
    listening.wait()
    assert not streams.opened[0].closed
    listening.close()
    assert streams.opened[0].closed


def test_removing_the_song_being_heard_stops_it(qtbot: QtBot, window_with_song: MainWindow) -> None:
    window = window_with_song
    panel = window.song_panel
    panel.listening.output_factory = FakeOutput
    select_song(window)
    with qtbot.waitSignal(panel.listening.started, timeout=TIMEOUT_MS):
        panel.listen.click()
    window.music_strip.remove_selected()
    assert panel.listening.song_id is None


def test_an_unexpected_waveform_error_does_not_leave_it_reading(qtbot: QtBot, tmp_path: Path) -> None:
    def broken_reader(_path: Path, _points: int) -> object:
        raise ValueError("unexpected")

    loader = WaveformLoader(reader=broken_reader)  # pyright: ignore[reportArgumentType]
    with qtbot.waitSignal(loader.ready, timeout=TIMEOUT_MS) as ready:
        loader.request(tmp_path / "a.wav")
    args = ready.args
    assert args is not None
    assert args[1] is None and args[2]
    loader.wait()


def test_a_song_that_could_not_be_read_is_read_again_when_selected(
    qtbot: QtBot, window_with_song: MainWindow
) -> None:
    window = window_with_song
    panel = window.song_panel
    real_reader = panel.waveforms._reader  # pyright: ignore[reportPrivateUsage]
    calls: list[Path] = []

    def first_fails(path: Path, points: int) -> object:
        calls.append(path)
        if len(calls) == 1:
            raise PassiMakerError("ffmpeg.file_not_found")
        return real_reader(path, points)

    panel.waveforms._reader = first_fails  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    select_song(window)
    qtbot.waitUntil(lambda: bool(panel.problem.text()), timeout=TIMEOUT_MS)
    panel.show_song(None)
    panel.show_song("s1")  # the file is back
    qtbot.waitUntil(lambda: panel.trim_bar.peaks is not None, timeout=TIMEOUT_MS)
    assert len(calls) == 2
    assert panel.problem.text() == ""


def test_editing_one_control_does_not_round_the_others(window_with_song: MainWindow) -> None:
    window = window_with_song
    exact = replace(song(window), trim_end_s=5.25, fade_in=Fade(True, 2.25))
    window.controller.execute(UpdateSong(exact))
    select_song(window)
    panel = window.song_panel
    panel.trim_start.setValue(1.0)
    assert song(window).trim_start_s == pytest.approx(1.0)
    assert song(window).trim_end_s == 5.25  # not 5,2 or 5,3
    panel.fade_out_enabled.setChecked(not panel.fade_out_enabled.isChecked())
    assert song(window).fade_in.seconds == 2.25
