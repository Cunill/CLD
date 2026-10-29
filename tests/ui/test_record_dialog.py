"""C10: the "Grava el que sona" window (ESPECIFICACIO §1.7 ter, annex PLA_GRAVACIO §2), with the fake backend.

No test opens a sound card: the capture is tests/fakes/recorder.py (it plays its script as fast as
it is read, then holds) and the conversion a fake that writes a small file, except the last test,
which goes through the real FFmpeg into the project. Every test checks that no temporary WAV is
left behind (G1).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from passimaker.common import CancelToken, ProgressCallback
from passimaker.ffmpeg import FfmpegError, Mp3Tags
from passimaker.i18n import message
from passimaker.model import defaults
from passimaker.recorder import (
    ERROR_DEVICE,
    ERROR_DEVICE_LOST,
    ERROR_DISK_FULL,
    ERROR_MAX_DURATION,
    ERROR_MICROPHONE_DENIED,
    ERROR_NO_DEVICE,
    ERROR_NO_SPACE,
    ERROR_SILENT,
    TEMP_PREFIX,
    AudioSource,
    RecorderDeviceError,
    RecorderMicrophoneDeniedError,
    RecorderNoDeviceError,
    RecorderState,
    RecordingSettings,
    StopReason,
    capture,
)
from passimaker.ui import app
from passimaker.ui.main_window import MainWindow
from passimaker.ui.record_dialog import (
    Phase,
    RecordDialogs,
    RecordWindow,
    forget_choices,
    gigabytes,
    song_title,
)
from passimaker.ui.wave_view import IDLE_COLOR, OVERVIEW_COLOR, RECORDING_COLOR, WaveMode
from tests.fakes.recorder import (
    HEADPHONES,
    MICROPHONE,
    SPEAKERS,
    ChangeDefault,
    Disconnect,
    Fail,
    FakeCaptureBackend,
    FakeStream,
    Segment,
    Silence,
    Tone,
)

pytestmark = pytest.mark.ui

WAIT_MS = 5_000
LOTS_OF_SPACE = 100 * 1024**3


@pytest.fixture(autouse=True)
def fresh_run(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test is a new run of the program (nothing remembered) with plenty of disk space."""
    forget_choices()
    monkeypatch.setattr(capture, "free_bytes", lambda folder: LOTS_OF_SPACE)
    yield
    forget_choices()


@pytest.fixture
def temp(tmp_path: Path) -> Path:
    made = tmp_path / "temp"
    made.mkdir()
    return made


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    made = tmp_path / "Música"
    made.mkdir()
    return made


@pytest.fixture
def added() -> list[list[Path]]:
    return []


class FakeQuestions:
    def __init__(self, path: Path | None = None, discard: bool = True, close: bool = True) -> None:
        self.path = path
        """What the save dialog answers (None: cancelled)."""
        self.discard = discard
        self.close = close
        self.suggested: list[Path] = []
        self.asked_discard = 0
        self.asked_close = 0

    def choose_recording_path(self, suggested: Path) -> Path | None:
        self.suggested.append(suggested)
        return self.path

    def confirm_discard_recording(self) -> bool:
        self.asked_discard += 1
        return self.discard

    def confirm_close_recording(self) -> bool:
        self.asked_close += 1
        return self.close


class FakeConverter:
    """Writes a small file instead of calling FFmpeg; `gate` holds it, `error` makes it fail."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, int, Mp3Tags]] = []
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.error: BaseException | None = None

    def __call__(
        self,
        source: Path,
        dest: Path,
        bitrate_kbps: int,
        tags: Mp3Tags,
        progress: ProgressCallback | None = None,
        cancel: CancelToken | None = None,
    ) -> None:
        assert source.is_file()
        self.calls.append((source, dest, bitrate_kbps, tags))
        self.started.set()
        if self.gate is not None:
            while not self.gate.wait(0.01):
                if cancel is not None and cancel.cancelled:
                    return
        if self.error is not None:
            raise self.error
        if progress is not None:
            progress(1, 2)
        dest.write_bytes(b"mp3")
        if progress is not None:
            progress(2, 2)


def make_window(
    qtbot: QtBot,
    backend: FakeCaptureBackend,
    questions: FakeQuestions,
    added: list[list[Path]],
    temp: Path,
    convert: FakeConverter | None = None,
) -> RecordWindow:
    window = RecordWindow(
        questions,
        lambda paths: added.append(list(paths)),
        backend=backend,
        convert=convert if convert is not None else FakeConverter(),
        temp_dir=temp,
    )
    window.now = lambda: datetime(2026, 10, 25, 18, 30)
    window.free_space = lambda folder: LOTS_OF_SPACE
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.phase is not Phase.LOADING and not window.busy, timeout=WAIT_MS)
    return window


def temp_wavs(temp: Path) -> list[Path]:
    return sorted(temp.glob(f"{TEMP_PREFIX}*"))


def settle(qtbot: QtBot, window: RecordWindow) -> None:
    qtbot.waitUntil(lambda: not window.busy, timeout=WAIT_MS)


def start_recording(
    qtbot: QtBot, window: RecordWindow, backend: FakeCaptureBackend, script: Sequence[Segment]
) -> None:
    """[● Grava] with `script` playing (the monitor already holds: the recorder gets a new stream)."""
    backend.script = list(script)
    window.record_button.click()
    qtbot.waitUntil(lambda: window.phase is not Phase.STARTING, timeout=WAIT_MS)


def recording_until(qtbot: QtBot, window: RecordWindow, condition: Callable[[], bool]) -> None:
    qtbot.waitUntil(condition, timeout=WAIT_MS)


def stop_and_wait(qtbot: QtBot, window: RecordWindow) -> None:
    window.stop_button.click()
    qtbot.waitUntil(lambda: window.phase not in (Phase.STOPPING, Phase.CONVERTING), timeout=WAIT_MS)
    settle(qtbot, window)


def elapsed(window: RecordWindow) -> float:
    recorder = window.recorder
    return recorder.elapsed_s if recorder is not None else 0.0


# --- Sources and monitor ---------------------------------------------------------------------------


def test_sources_are_listed_off_the_ui_thread_outputs_first_and_monitored(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend(sources=(MICROPHONE, HEADPHONES, SPEAKERS), script=[Tone(0.5)])
    listed_in: list[threading.Thread] = []
    original = backend.list_sources

    def list_sources() -> tuple[object, ...]:
        listed_in.append(threading.current_thread())
        return original()

    backend.list_sources = list_sources  # type: ignore[method-assign]
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    assert listed_in and listed_in[0] is not threading.main_thread()
    assert window.phase is Phase.READY
    texts = [window.source_combo.itemText(i).strip() for i in range(window.source_combo.count())]
    assert texts == [
        "So de l'ordinador",
        "Altaveus (Realtek) — per defecte",
        "Auriculars X-SMC01",
        "Micròfon i entrada de línia",
        "Micròfon (Webcam C170) — per defecte",
    ]
    assert window.selected_source() == SPEAKERS
    assert window.monitor is not None
    qtbot.waitUntil(lambda: window.wave.following and window.wave.live_columns.shape[0] > 0, timeout=WAIT_MS)
    assert window.wave.wave_color() == IDLE_COLOR
    assert temp_wavs(temp) == []  # the monitor never writes


def test_the_microphone_is_only_opened_when_chosen(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend(script=[Tone(0.2)])
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    settle(qtbot, window)
    assert {stream._source.id for stream in backend.streams} == {SPEAKERS.id}
    window.select_source(MICROPHONE.id)
    settle(qtbot, window)
    assert backend.streams[-1]._source == MICROPHONE
    assert window.wave.channels == 1


def test_the_choice_is_remembered_while_the_program_runs(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    window = make_window(qtbot, FakeCaptureBackend(), FakeQuestions(), added, temp)
    window.select_source(HEADPHONES.id)
    window.close()
    other = make_window(qtbot, FakeCaptureBackend(), FakeQuestions(), added, temp)
    assert other.selected_source() == HEADPHONES
    forget_choices()  # a new run of the program
    third = make_window(qtbot, FakeCaptureBackend(), FakeQuestions(), added, temp)
    assert third.selected_source() == SPEAKERS


def test_no_output_says_so(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    window = make_window(qtbot, FakeCaptureBackend(sources=()), FakeQuestions(), added, temp)
    assert window.phase is Phase.NO_SOURCES
    assert window.message_text() == message(ERROR_NO_DEVICE)
    assert not window.record_button.isEnabled()


def test_a_failing_sound_system_while_listing(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend(list_error=RecorderDeviceError("fake"))
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    assert window.phase is Phase.NO_SOURCES
    assert window.message_text() == message(ERROR_DEVICE)


def test_microphone_denied_says_where_to_allow_it(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    backend.open_error = RecorderMicrophoneDeniedError("0x80070005")
    window.select_source(MICROPHONE.id)
    settle(qtbot, window)
    assert window.message_text() == message(ERROR_MICROPHONE_DENIED)
    assert "Privadesa" in window.message_text()
    window.record_button.click()
    qtbot.waitUntil(lambda: window.phase is Phase.READY, timeout=WAIT_MS)
    settle(qtbot, window)
    assert window.message_text() == message(ERROR_MICROPHONE_DENIED)
    assert temp_wavs(temp) == []


def test_a_change_of_output_while_monitoring_lists_the_sources_again(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend(script=[Tone(1.1), ChangeDefault(HEADPHONES.id), Tone(1.1)])
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    qtbot.waitUntil(lambda: "ha canviat" in window.message_text(), timeout=WAIT_MS)
    settle(qtbot, window)
    assert window.phase is Phase.READY


# --- Recording and saving --------------------------------------------------------------------------


def test_record_stop_save_and_add_to_the_project(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    convert = FakeConverter()
    questions = FakeQuestions(path=folder / "La meva cançó.mp3")
    window = make_window(qtbot, backend, questions, added, temp, convert)
    start_recording(qtbot, window, backend, [Silence(1.0), Tone(2.0), Silence(1.0)])
    assert window.phase is Phase.RECORDING
    assert not window.source_combo.isEnabled()
    assert not window.record_button.isEnabled()
    recording_until(qtbot, window, lambda: elapsed(window) >= 3.19)
    qtbot.waitUntil(lambda: window.wave.recording, timeout=WAIT_MS)
    assert window.wave.wave_color() == RECORDING_COLOR
    window.tick()
    assert window.time_label.text() == "● 0:03"
    assert window.free_label.text() == "Lliure: 107 GB"
    stop_and_wait(qtbot, window)
    assert [path.name for path in questions.suggested] == ["Gravació 25-10-2026 18.30.mp3"]
    assert len(convert.calls) == 1
    source, dest, bitrate, tags = convert.calls[0]
    assert dest == folder / "La meva cançó.mp3"
    assert bitrate == defaults.RECORD_MP3_BITRATE_KBPS == 192
    assert tags.title == "La meva cançó"
    assert not source.exists()  # the temporary WAV goes once saved
    assert added == [[dest]]
    assert window.saved == [dest]
    assert window.message_text() == "Desada: La meva cançó.mp3"
    assert window.phase is Phase.READY
    assert temp_wavs(temp) == []


def test_stopping_shows_the_whole_wave_with_the_trimmed_silence_shaded(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(path=None)  # stays pending: the overview stays on screen
    settings = RecordingSettings(start_when_sound=False, silence_stop=False)
    window = make_window(qtbot, backend, questions, added, temp)
    window.settings = lambda: settings  # type: ignore[method-assign]
    start_recording(qtbot, window, backend, [Silence(2.0), Tone(4.0), Silence(2.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 7.99)
    stop_and_wait(qtbot, window)
    assert window.phase is Phase.PENDING
    result = window.pending_result
    assert result is not None and result.stop_reason is StopReason.USER
    assert window.wave.mode is WaveMode.OVERVIEW
    assert window.wave.wave_color() == OVERVIEW_COLOR
    start, end = window.wave.trimmed_fractions
    assert start == pytest.approx((2.0 - defaults.RECORD_TRIM_MARGIN_S) / 8.0, abs=0.01)
    assert end == pytest.approx((2.0 - defaults.RECORD_TRIM_MARGIN_S) / 8.0, abs=0.01)
    assert len(window.wave.shaded_rects(0)) == 2
    assert window.time_label.text() == "0:04"
    assert "encara no s'ha desat" in window.message_text()
    assert window.save_button.isVisible() and window.discard_button.isEnabled()
    assert len(temp_wavs(temp)) == 1  # kept for [Desa…]
    window.discard_button.click()
    settle(qtbot, window)
    assert temp_wavs(temp) == []


def test_cancelling_the_save_dialog_keeps_it_and_desa_saves_it_later(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(path=None)
    window = make_window(qtbot, backend, questions, added, temp)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    stop_and_wait(qtbot, window)
    assert window.phase is Phase.PENDING
    questions.path = folder / "Primera"
    window.save_button.click()
    settle(qtbot, window)
    assert added == [[folder / "Primera.mp3"]]
    assert temp_wavs(temp) == []
    # The next time the last folder is proposed, and an existing name is never overwritten.
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    stop_and_wait(qtbot, window)
    assert questions.suggested[-1].parent == folder
    assert added[-1] == [folder / "Primera (2).mp3"]


def test_without_add_to_project_the_song_is_only_saved(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(path=folder / "x.mp3"), added, temp)
    window.add_to_project.setChecked(False)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    stop_and_wait(qtbot, window)
    assert (folder / "x.mp3").is_file()
    assert added == []


def test_a_failed_conversion_keeps_the_recording_to_try_again(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    convert = FakeConverter()
    convert.error = FfmpegError("ffmpeg.disk_full", "fake")
    window = make_window(qtbot, backend, FakeQuestions(path=folder / "x.mp3"), added, temp, convert)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    stop_and_wait(qtbot, window)
    assert window.phase is Phase.PENDING
    assert window.message_text() == message("ffmpeg.disk_full")
    assert len(temp_wavs(temp)) == 1
    convert.error = None
    window.save_button.click()
    settle(qtbot, window)
    assert added == [[folder / "x.mp3"]]
    assert temp_wavs(temp) == []


def test_the_conversion_runs_off_the_ui_thread_with_progress(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    convert = FakeConverter()
    convert.gate = threading.Event()
    window = make_window(qtbot, backend, FakeQuestions(path=folder / "x.mp3"), added, temp, convert)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    window.stop_button.click()
    qtbot.waitUntil(lambda: window.phase is Phase.CONVERTING, timeout=WAIT_MS)
    assert window.progress.isVisible()
    assert window.message_text() == "Convertint a MP3…"
    convert.gate.set()
    qtbot.waitUntil(lambda: window.phase is Phase.READY, timeout=WAIT_MS)
    settle(qtbot, window)
    assert added == [[folder / "x.mp3"]]


# --- "Comença quan soni" and the automatic stop ----------------------------------------------------


def test_start_when_sound_waits_in_grey_then_records_in_red(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    assert window.start_when_sound.isChecked()
    start_recording(qtbot, window, backend, [Silence(1.0)])
    recording_until(qtbot, window, lambda: window.wave.live_columns.shape[0] >= 50)
    window.tick()
    assert window.recorder is not None and window.recorder.state is RecorderState.WAITING
    assert window.time_label.text() == "Esperant que soni…"
    assert window.wave.wave_color() == IDLE_COLOR
    assert elapsed(window) == 0.0
    window.discard_button.click()
    settle(qtbot, window)
    assert temp_wavs(temp) == []


def test_the_automatic_stop_for_silence_saves_the_recording(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(path=folder / "auto.mp3"), added, temp)
    window.silence_seconds.setValue(1)
    assert window.settings().silence_stop_s == 1.0
    start_recording(qtbot, window, backend, [Tone(1.0), Silence(1.5)])
    qtbot.waitUntil(lambda: bool(added), timeout=WAIT_MS)
    settle(qtbot, window)
    assert added == [[folder / "auto.mp3"]]
    assert window.phase is Phase.READY
    assert temp_wavs(temp) == []


def test_the_options_reach_the_recorder(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    window = make_window(qtbot, FakeCaptureBackend(), FakeQuestions(), added, temp)
    window.start_when_sound.setChecked(False)
    window.silence_stop.setChecked(False)
    assert not window.silence_seconds.isEnabled()
    settings = window.settings()
    assert not settings.start_when_sound
    assert not settings.silence_stop
    assert settings.max_duration_s == defaults.RECORD_MAX_DURATION_S
    assert window.silence_seconds.minimum() == defaults.RECORD_SILENCE_STOP_RANGE.minimum
    assert window.silence_seconds.maximum() == defaults.RECORD_SILENCE_STOP_RANGE.maximum


# --- Errors (G1, G5) -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("script", "key"),
    [
        ([Tone(1.0), Disconnect()], ERROR_DEVICE_LOST),
        ([Tone(1.5), ChangeDefault(HEADPHONES.id), Tone(1.5)], ERROR_DEVICE_LOST),
        ([Tone(1.0), Fail(RuntimeError("driver"))], ERROR_DEVICE),
    ],
    ids=["disconnected", "output-changed", "sound-system"],
)
def test_an_interruption_deletes_the_recording_and_says_why(
    qtbot: QtBot, temp: Path, added: list[list[Path]], script: list[Segment], key: str
) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(path=temp / "never.mp3")
    window = make_window(qtbot, backend, questions, added, temp)
    start_recording(qtbot, window, backend, script)
    qtbot.waitUntil(lambda: window.message_text() == message(key), timeout=WAIT_MS)
    settle(qtbot, window)
    assert window.phase is Phase.READY
    assert questions.suggested == []  # never asked to save
    assert added == []
    assert temp_wavs(temp) == []
    assert window.monitor is not None  # back to the monitor


@dataclass
class VanishingBackend(FakeCaptureBackend):
    """Bluetooth headphones switched off while recording: once `vanish` is opened for recording,
    they leave the list and can no longer be opened (manual test of 29/10/2026)."""

    vanish: str | None = None
    gone: set[str] = field(default_factory=set[str])

    def list_sources(self) -> tuple[AudioSource, ...]:
        return tuple(source for source in super().list_sources() if source.id not in self.gone)

    def open(self, source: AudioSource) -> FakeStream:
        if source.id in self.gone:
            raise RecorderNoDeviceError(source.name)
        stream = super().open(source)
        if source.id == self.vanish:
            self.gone.add(source.id)
        return stream


def test_switching_off_the_headphones_keeps_the_message_and_lists_the_sources_again(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = VanishingBackend()
    questions = FakeQuestions(path=temp / "never.mp3")
    window = make_window(qtbot, backend, questions, added, temp)
    window.select_source(HEADPHONES.id)
    settle(qtbot, window)
    backend.vanish = HEADPHONES.id
    start_recording(qtbot, window, backend, [Tone(1.0), Disconnect()])
    qtbot.waitUntil(lambda: window.phase is Phase.READY and window.monitor is not None, timeout=WAIT_MS)
    settle(qtbot, window)
    assert window.message_text() == message(ERROR_DEVICE_LOST)  # not "No s'ha trobat cap sortida"
    assert HEADPHONES not in window.sources()
    assert window.selected_source() == SPEAKERS
    assert window.monitor is not None and window.monitor.source == SPEAKERS
    assert questions.suggested == []
    assert temp_wavs(temp) == []


def test_disk_full_while_recording(
    qtbot: QtBot, temp: Path, added: list[list[Path]], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    space = iter([LOTS_OF_SPACE])
    monkeypatch.setattr(capture, "free_bytes", lambda folder: next(space, 1024))
    start_recording(qtbot, window, backend, [Tone(2.0)])
    qtbot.waitUntil(lambda: window.message_text() == message(ERROR_DISK_FULL), timeout=WAIT_MS)
    settle(qtbot, window)
    assert temp_wavs(temp) == []


def test_not_enough_space_to_start(
    qtbot: QtBot, temp: Path, added: list[list[Path]], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    monkeypatch.setattr(capture, "free_bytes", lambda folder: defaults.RECORD_MIN_FREE_BYTES - 1)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    settle(qtbot, window)
    assert window.phase is Phase.READY
    assert window.message_text() == message(ERROR_NO_SPACE)
    assert temp_wavs(temp) == []


def test_the_maximum_duration_turns_the_time_orange_then_deletes_it(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(path=temp / "never.mp3"), added, temp)
    limit = defaults.RECORD_MAX_WARNING_S + 3.0
    window.settings = lambda: RecordingSettings(  # type: ignore[method-assign]
        start_when_sound=False, silence_stop=False, max_duration_s=limit
    )
    start_recording(qtbot, window, backend, [Tone(1.0), Silence(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 1.99)
    window.tick()
    assert not window.time_is_warning()
    window.discard_button.click()
    settle(qtbot, window)
    start_recording(qtbot, window, backend, [Tone(1.0), Silence(3.5)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 4.49)
    window.tick()
    assert window.time_is_warning()
    window.discard_button.click()
    settle(qtbot, window)
    start_recording(qtbot, window, backend, [Tone(1.0), Silence(limit)])
    qtbot.waitUntil(lambda: window.message_text() == message(ERROR_MAX_DURATION), timeout=WAIT_MS)
    settle(qtbot, window)
    assert added == []
    assert temp_wavs(temp) == []


def test_nothing_recorded_says_so(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(path=temp / "never.mp3")
    window = make_window(qtbot, backend, questions, added, temp)
    window.start_when_sound.setChecked(False)
    start_recording(qtbot, window, backend, [Silence(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    stop_and_wait(qtbot, window)
    assert window.message_text() == message(ERROR_SILENT)
    assert questions.suggested == []
    assert temp_wavs(temp) == []


def test_every_error_of_the_recorder_has_catalan_text() -> None:
    for key in (
        ERROR_NO_DEVICE,
        ERROR_DEVICE_LOST,
        ERROR_SILENT,
        ERROR_DISK_FULL,
        ERROR_NO_SPACE,
        ERROR_MAX_DURATION,
        ERROR_DEVICE,
        ERROR_MICROPHONE_DENIED,
    ):
        assert message(key) != key


# --- Discarding and closing ------------------------------------------------------------------------


def test_discarding_a_short_recording_does_not_ask(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions()
    window = make_window(qtbot, backend, questions, added, temp)
    start_recording(qtbot, window, backend, [Tone(2.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 1.99)
    window.discard_button.click()
    settle(qtbot, window)
    assert questions.asked_discard == 0
    assert window.message_text() == "S'ha descartat la gravació."
    assert window.phase is Phase.READY
    assert temp_wavs(temp) == []


def test_discarding_a_long_recording_asks_first(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(discard=False)
    window = make_window(qtbot, backend, questions, added, temp)
    seconds = defaults.RECORD_DISCARD_CONFIRM_S + 1.0
    start_recording(qtbot, window, backend, [Tone(seconds)])
    recording_until(qtbot, window, lambda: elapsed(window) >= seconds)
    window.discard_button.click()
    assert questions.asked_discard == 1
    assert window.phase is Phase.RECORDING  # kept
    questions.discard = True
    window.discard_button.click()
    settle(qtbot, window)
    assert questions.asked_discard == 2
    assert window.phase is Phase.READY
    assert temp_wavs(temp) == []


def test_closing_while_recording_asks_and_deletes_it(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(close=False)
    window = make_window(qtbot, backend, questions, added, temp)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    assert not window.close()
    assert questions.asked_close == 1
    assert window.isVisible() and window.phase is Phase.RECORDING
    questions.close = True
    assert window.close()
    assert questions.asked_close == 2
    assert temp_wavs(temp) == []  # deleted before close() returns (G1)
    assert added == []


def test_closing_without_a_recording_does_not_ask(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(close=False)
    window = make_window(qtbot, backend, questions, added, temp)
    assert window.close()
    assert questions.asked_close == 0
    assert all(stream.closed for stream in backend.streams)  # the monitor stopped


def test_closing_a_kept_recording_asks_and_deletes_it(
    qtbot: QtBot, temp: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    questions = FakeQuestions(path=None)
    window = make_window(qtbot, backend, questions, added, temp)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    stop_and_wait(qtbot, window)
    assert len(temp_wavs(temp)) == 1
    assert window.close()
    assert questions.asked_close == 1
    assert temp_wavs(temp) == []


def test_closing_while_converting_leaves_no_file(
    qtbot: QtBot, temp: Path, folder: Path, added: list[list[Path]]
) -> None:
    backend = FakeCaptureBackend()
    convert = FakeConverter()
    convert.gate = threading.Event()
    window = make_window(qtbot, backend, FakeQuestions(path=folder / "x.mp3"), added, temp, convert)
    start_recording(qtbot, window, backend, [Tone(1.0)])
    recording_until(qtbot, window, lambda: elapsed(window) >= 0.99)
    window.stop_button.click()
    qtbot.waitUntil(convert.started.is_set, timeout=WAIT_MS)
    assert window.close()
    assert temp_wavs(temp) == []
    assert list(folder.iterdir()) == []
    qtbot.wait(50)
    assert added == []


def test_reopening_after_closing_monitors_again(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    backend = FakeCaptureBackend()
    window = make_window(qtbot, backend, FakeQuestions(), added, temp)
    window.close()
    assert window.monitor is None
    window.show()
    qtbot.waitUntil(lambda: window.phase is Phase.READY and window.monitor is not None, timeout=WAIT_MS)


# --- From the main window --------------------------------------------------------------------------


def test_the_music_menu_opens_the_window_without_any_notice(window: MainWindow, temp: Path) -> None:
    assert window.music_record_action.text() == "Grava el que sona…"
    assert window.music_record_action in window.music_menu.actions()
    window.record_backend = FakeCaptureBackend()
    window.record_questions = FakeQuestions()
    window.music_record_action.trigger()
    recorder = window.record_window
    assert recorder is not None and recorder.isVisible()
    assert not recorder.isModal()
    assert recorder.windowTitle() == "Grava el que sona"
    window.music_record_action.trigger()
    assert window.record_window is recorder  # the same window again


def test_closing_the_program_while_recording_asks(
    qtbot: QtBot, window: MainWindow, temp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(temp))
    backend = FakeCaptureBackend()
    questions = FakeQuestions(close=False)
    window.record_backend = backend
    window.record_questions = questions
    window.music_record_action.trigger()
    recorder = window.record_window
    assert recorder is not None
    qtbot.waitUntil(lambda: recorder.phase is Phase.READY and not recorder.busy, timeout=WAIT_MS)
    start_recording(qtbot, recorder, backend, [Tone(1.0)])
    recording_until(qtbot, recorder, lambda: elapsed(recorder) >= 0.99)
    assert not window.close()
    assert window.isVisible() and recorder.phase is Phase.RECORDING
    questions.close = True
    assert window.close()
    assert temp_wavs(temp) == []


def test_a_recording_reaches_the_controller_as_add_songs(
    qtbot: QtBot, window: MainWindow, temp: Path, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real convert_to_mp3 and the window's add_songs: the song is in the project; Ctrl+Z removes it."""
    monkeypatch.setattr("tempfile.tempdir", str(temp))
    backend = FakeCaptureBackend()
    window.record_backend = backend
    window.record_questions = FakeQuestions(path=folder / "Gravada.mp3")
    window.music_record_action.trigger()
    recorder = window.record_window
    assert recorder is not None
    qtbot.waitUntil(lambda: recorder.phase is Phase.READY and not recorder.busy, timeout=WAIT_MS)
    start_recording(qtbot, recorder, backend, [Tone(1.0)])
    recording_until(qtbot, recorder, lambda: elapsed(recorder) >= 0.99)
    recorder.stop_button.click()
    qtbot.waitUntil(lambda: len(window.controller.project.music.songs) == 1, timeout=20_000)
    song = window.controller.project.music.songs[0]
    assert song.path == folder / "Gravada.mp3"
    assert song.path.is_file()
    assert temp_wavs(temp) == []
    window.undo()
    assert window.controller.project.music.songs == ()


# --- Leftovers and texts ---------------------------------------------------------------------------


def test_opening_the_program_deletes_leftovers_off_the_ui_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    leftover = tmp_path / f"{TEMP_PREFIX}abc.wav"
    leftover.write_bytes(b"RIFF")
    other = tmp_path / "other.wav"
    other.write_bytes(b"RIFF")
    thread = app.remove_recording_leftovers()
    assert thread is not threading.current_thread()
    thread.join(5)
    assert not leftover.exists()
    assert other.exists()


def test_the_window_texts_are_catalan(qtbot: QtBot, temp: Path, added: list[list[Path]]) -> None:
    window = make_window(qtbot, FakeCaptureBackend(), FakeQuestions(), added, temp)
    buttons = {button.text() for button in window.findChildren(QPushButton)}
    assert {"● Grava", "■ Atura", "Descarta", "Desa…"} <= buttons
    boxes = {box.text() for box in window.findChildren(QCheckBox)}
    assert {"Comença quan soni", "Atura't després de", "Afegeix al projecte en acabar"} <= boxes
    assert window.add_to_project.isChecked()
    assert window.silence_seconds.suffix() == " s de silenci"
    labels = " ".join(label.text() for label in window.findChildren(QLabel))
    assert "Puja el volum de Windows i el de l'aplicació que sona" in labels
    assert "avís" not in labels.lower()  # no notice (G2)
    assert window.suggested_name() == "Gravació 25-10-2026 18.30"


def test_helpers() -> None:
    assert gigabytes(112 * 10**9) == "112 GB"
    assert gigabytes(8_400_000_000) == "8,4 GB"
    assert song_title(Path("a/Cançó.MP3")) == "Cançó"
    assert song_title(Path("a/v1.2")) == "v1.2"


def test_the_real_questions_are_dialogs(qtbot: QtBot) -> None:
    dialogs = RecordDialogs()
    qtbot.addWidget(dialogs)
    assert callable(dialogs.choose_recording_path)
    assert callable(dialogs.confirm_close_recording)
    assert callable(dialogs.confirm_discard_recording)
