"""The "Grava el que sona" window (ESPECIFICACIO §1.7 ter, annex PLA_GRAVACIO §2, decision 0013, block C10).

- Not modal and without any notice (G2). The sources come from recorder.list_sources(): the
  sound of the computer first (the default output first), then the microphone and line inputs,
  which are only opened if the user picks them (G6). The choice is remembered while the program
  runs.
- Before recording, a Monitor shows the waves and the level (nothing is written). [● Grava]
  starts a Recorder; [■ Atura] (or the automatic stop for silence) keeps the recording, shows the
  whole wave with the trimmed silence shaded, asks where to save it (the last folder is proposed)
  and converts it to MP3. Any interruption deletes it and says why (G1, G5); [Descarta] too.
- Every call that may block (listing, opening, stopping and discarding a capture, converting) runs
  in a worker thread (rule 6): the device ones in a single thread, one after the other, so a Monitor
  and a Recorder never fight for the same device. The results come back through signals.

The window takes the capture backend (tests/fakes/recorder.py in the tests) and the converter.
"""

from __future__ import annotations

import errno
import logging
import shutil
import tempfile
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import CancelledError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol, cast

from PySide6.QtCore import QObject, QRunnable, QStandardPaths, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from passimaker.common import CancelToken, PassiMakerError
from passimaker.common.files import EXTENSION, safe_target_path
from passimaker.ffmpeg import Mp3Tags, convert_to_mp3
from passimaker.i18n import message
from passimaker.model import defaults
from passimaker.recorder import (
    ERROR_DEVICE,
    ERROR_NO_DEVICE,
    AudioSource,
    CaptureBackend,
    Monitor,
    Recorder,
    RecorderState,
    RecordingResult,
    RecordingSettings,
    SourceKind,
    list_sources,
)
from passimaker.ui.dialogs import DialogQuestions
from passimaker.ui.formatting import clock
from passimaker.ui.wave_view import WaveView
from passimaker.ui.youtube_dialog import Converter

_log = logging.getLogger(__name__)

CLOSE_WAIT_MS = 10_000
"""Closing: how long to wait for the capture to end and its files to be deleted (G1)."""
PROGRESS_STEPS = 1000
FREE_SPACE_EVERY_S = 1.0
GIGABYTE = 1_000_000_000
GIGABYTE_SYMBOL = " GB"
"""Unit symbol, not prose (like formatting.MEGABYTE_SYMBOL)."""
WARNING_STYLE = "color: #e07000; font-weight: bold;"
"""The elapsed time, RECORD_MAX_WARNING_S before the maximum (G5)."""
RECORDING_STYLE = "color: #d03030; font-weight: bold;"
ERROR_STYLE = "color: #b22;"


@dataclass
class _Remembered:
    """What the window remembers while the program runs (not saved anywhere)."""

    source_id: str | None = None
    folder: Path | None = None


_remembered = _Remembered()


def forget_choices() -> None:
    """A new run of the program (the tests start from nothing)."""
    _remembered.source_id = None
    _remembered.folder = None


def gigabytes(size_bytes: int) -> str:
    """ "112 GB", or "8,4 GB" under ten."""
    value = size_bytes / GIGABYTE
    text = f"{value:.0f}" if value >= 10 else f"{value:.1f}".replace(".", ",")
    return text + GIGABYTE_SYMBOL


def error_text(error: BaseException) -> str:
    """The Catalan text of an error: the recorder's and FFmpeg's by key; a disk error as FFmpeg's
    writing errors; anything unexpected as an error of the sound system."""
    if isinstance(error, PassiMakerError):
        return message(error.message_key)
    if isinstance(error, OSError):
        return message("ffmpeg.disk_full" if error.errno == errno.ENOSPC else "ffmpeg.write_error")
    return message(ERROR_DEVICE)


def log_error(what: str, error: BaseException) -> None:
    detail = error.detail if isinstance(error, PassiMakerError) else ""
    _log.log(logging.WARNING, "Gravació, %s: %r %s", what, error, detail)


def song_title(path: Path) -> str:
    """The name the user typed, without ".mp3" (any other dot stays part of the name)."""
    return path.stem if path.suffix.lower() == EXTENSION else path.name


# --- Questions --------------------------------------------------------------------------------------


class RecordQuestions(Protocol):
    """What the recording window asks the user (the tests answer without dialogs)."""

    def choose_recording_path(self, suggested: Path) -> Path | None:
        """Where to save the recording, starting at `suggested` (folder and name); None: not now."""
        ...

    def confirm_discard_recording(self) -> bool:
        """[Descarta] on a recording longer than RECORD_DISCARD_CONFIRM_S."""
        ...

    def confirm_close_recording(self) -> bool:
        """Closing the window or the program with a recording: "La gravació s'esborrarà…"."""
        ...


class RecordDialogs(DialogQuestions):
    """The real questions of the recording window, as modal dialogs."""

    def confirm_discard_recording(self) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Grava el que sona"),
            self.tr("Vols descartar la gravació? S'esborrarà sense desar-la."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def confirm_close_recording(self) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Grava el que sona"),
            self.tr("La gravació s'esborrarà. Vols aturar-la i sortir?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes


# --- Work in other threads --------------------------------------------------------------------------


class _TaskSignals(QObject):
    """One per window, for every task: a QObject per task deleted with deleteLater() while the
    worker thread still drops its Python wrapper crashed PySide (block C10)."""

    done = Signal(int, object, object)
    """(task, result, error): one of result and error is None."""
    progress = Signal(int, int, int)
    """(task, done, total)."""


class _Task(QRunnable):
    def __init__(self, task: int, work: Callable[[], object], signals: _TaskSignals | None) -> None:
        super().__init__()
        self._task = task
        self._work = work
        self._signals = signals

    def run(self) -> None:
        try:
            result = self._work()
        except BaseException as error:  # every failure goes back to the interface
            if self._signals is not None:
                self._signals.done.emit(self._task, None, error)
            else:
                _log.log(logging.WARNING, "Gravació, tancant: %r", error)
        else:
            if self._signals is not None:
                self._signals.done.emit(self._task, result, None)


@dataclass
class _Session:
    """One opening of the window: closing it abandons what is still on its way (G1)."""

    abandoned: threading.Event = field(default_factory=threading.Event)
    cancel: CancelToken = field(default_factory=CancelToken)


@dataclass(frozen=True)
class _Callbacks:
    """Where the answers of a task go, and the opening of the window it belongs to."""

    session: _Session
    done: Callable[[object, object], None]
    progress: Callable[[int, int], None] | None


class Phase(Enum):
    LOADING = "loading"
    """Listing the sources."""
    READY = "ready"
    """A source chosen (its Monitor running, if it could open); [● Grava] can start."""
    NO_SOURCES = "no_sources"
    STARTING = "starting"
    RECORDING = "recording"
    """Recording or waiting for the first sound."""
    STOPPING = "stopping"
    PENDING = "pending"
    """Stopped and kept, not saved yet (the folder was not chosen, or the conversion failed)."""
    CONVERTING = "converting"
    DISCARDING = "discarding"


HOLDS_A_RECORDING = frozenset(
    {Phase.STARTING, Phase.RECORDING, Phase.STOPPING, Phase.PENDING, Phase.CONVERTING}
)


# --- The window -------------------------------------------------------------------------------------


class RecordWindow(QWidget):
    """§1.7 ter: not modal, no notice (G2); the main window opens it from [+ Música ▾]."""

    def __init__(
        self,
        questions: RecordQuestions,
        add_songs: Callable[[Sequence[Path]], None],
        *,
        backend: CaptureBackend | None = None,
        convert: Converter = convert_to_mp3,
        temp_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.questions = questions
        self._add_songs = add_songs
        self.backend = backend
        """None: the real one (soundcard)."""
        self._convert = convert
        self._temp_dir = temp_dir
        self.now: Callable[[], datetime] = datetime.now
        """For the proposed name (the tests fix it)."""
        self.free_space: Callable[[Path], int] = lambda folder: shutil.disk_usage(folder).free
        self._devices = QThreadPool(self)
        self._devices.setMaxThreadCount(1)
        self._conversions = QThreadPool(self)
        self._conversions.setMaxThreadCount(1)
        self._session = _Session()
        self._phase = Phase.LOADING
        self._sources: tuple[AudioSource, ...] = ()
        self._monitor: Monitor | None = None
        self._recorder: Recorder | None = None
        self._result: RecordingResult | None = None
        self._pending_tasks = 0
        self._last_task = 0
        self._callbacks: dict[int, _Callbacks] = {}
        self._bus = _TaskSignals(self)
        self._bus.done.connect(self._on_task_done)
        self._bus.progress.connect(self._on_task_progress)
        self._listing = False
        self._notice = ""
        self._last_free_check = -FREE_SPACE_EVERY_S
        self._ticks = 0
        self.saved: list[Path] = []
        """The MP3s saved by this window (newest last)."""

        self.setWindowTitle(self.tr("Grava el que sona"))
        self.resize(720, 420)
        self.source_label = QLabel(self.tr("Origen:"))
        self.source_combo = QComboBox()
        self.source_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.wave = WaveView()
        self.time_label = QLabel()
        self.free_label = QLabel()
        self.start_when_sound = QCheckBox(self.tr("Comença quan soni"))
        self.start_when_sound.setChecked(defaults.RECORD_START_WHEN_SOUND)
        self.start_when_sound.setToolTip(self.tr("Espera que arribi el primer so per començar a desar"))
        self.silence_stop = QCheckBox(self.tr("Atura't després de"))
        self.silence_stop.setChecked(defaults.RECORD_SILENCE_STOP_ENABLED)
        self.silence_seconds = QSpinBox()
        silence_range = defaults.RECORD_SILENCE_STOP_RANGE
        self.silence_seconds.setRange(round(silence_range.minimum), round(silence_range.maximum))
        self.silence_seconds.setSingleStep(round(silence_range.step))
        self.silence_seconds.setValue(round(defaults.RECORD_SILENCE_STOP_S))
        self.silence_seconds.setSuffix(self.tr(" s de silenci"))
        self.tip = QLabel(
            self.tr(
                "Tanca o silencia les altres aplicacions: es grava tot el que sona a l'ordinador, també "
                "els avisos. Puja el volum de Windows i el de l'aplicació que sona: com més baixos, més "
                "fluixa queda la gravació."
            )
        )
        self.tip.setWordWrap(True)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, PROGRESS_STEPS)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.add_to_project = QCheckBox(self.tr("Afegeix al projecte en acabar"))
        self.add_to_project.setChecked(True)
        self.record_button = QPushButton(self.tr("● Grava"))
        self.stop_button = QPushButton(self.tr("■ Atura"))
        self.discard_button = QPushButton(self.tr("Descarta"))
        self.save_button = QPushButton(self.tr("Desa…"))
        self.save_button.setToolTip(self.tr("Tria on vols desar la gravació"))
        self._build_layout()

        self._ticker = QTimer(self)
        self._ticker.setInterval(round(1000 / defaults.RECORD_WAVE_REFRESH_HZ))
        self._ticker.timeout.connect(self.tick)
        self.source_combo.currentIndexChanged.connect(self._on_source_chosen)
        self.silence_stop.toggled.connect(self.silence_seconds.setEnabled)
        self.record_button.clicked.connect(self.record)
        self.stop_button.clicked.connect(self.stop)
        self.discard_button.clicked.connect(self.discard)
        self.save_button.clicked.connect(self.save_pending)
        self._set_phase(Phase.LOADING)

    def _build_layout(self) -> None:
        top = QHBoxLayout()
        top.addWidget(self.source_label)
        top.addWidget(self.source_combo, 1)
        status = QHBoxLayout()
        status.addWidget(self.time_label)
        status.addStretch(1)
        status.addWidget(self.free_label)
        options = QHBoxLayout()
        options.addWidget(self.start_when_sound)
        options.addSpacing(16)
        options.addWidget(self.silence_stop)
        options.addWidget(self.silence_seconds)
        options.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_to_project)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.discard_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.record_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.wave)
        layout.addLayout(status)
        layout.addLayout(options)
        layout.addWidget(self.tip)
        layout.addWidget(self.message_label)
        layout.addWidget(self.progress)
        layout.addStretch(1)
        layout.addLayout(buttons)

    # --- State, for the window and the tests ------------------------------------------------------

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def busy(self) -> bool:
        """Something is on its way in a worker thread."""
        return self._pending_tasks > 0

    @property
    def monitor(self) -> Monitor | None:
        return self._monitor

    @property
    def recorder(self) -> Recorder | None:
        return self._recorder

    @property
    def pending_result(self) -> RecordingResult | None:
        """The recording kept and not saved yet (Phase.PENDING and CONVERTING)."""
        return self._result

    def sources(self) -> tuple[AudioSource, ...]:
        return self._sources

    def selected_source(self) -> AudioSource | None:
        data = self.source_combo.currentData()
        return data if isinstance(data, AudioSource) else None

    def select_source(self, source_id: str) -> None:
        for index in range(self.source_combo.count()):
            data = self.source_combo.itemData(index)
            if isinstance(data, AudioSource) and data.id == source_id:
                self.source_combo.setCurrentIndex(index)
                return

    def message_text(self) -> str:
        return self.message_label.text() if self.message_label.isVisible() else ""

    def wait_for_work(self, milliseconds: int = CLOSE_WAIT_MS) -> bool:
        devices = self._devices.waitForDone(milliseconds)
        return self._conversions.waitForDone(milliseconds) and devices

    def settings(self) -> RecordingSettings:
        """The options of the window; the rest from defaults.py."""
        return RecordingSettings(
            start_when_sound=self.start_when_sound.isChecked(),
            silence_stop=self.silence_stop.isChecked(),
            silence_stop_s=float(self.silence_seconds.value()),
        )

    def suggested_name(self) -> str:
        """ "Gravació 25-10-2026 18.30" (§1.7 ter)."""
        return self.tr("Gravació {date}").format(date=f"{self.now():%d-%m-%Y %H.%M}")

    def suggested_folder(self) -> Path:
        """The last folder used while the program runs; the first time, the Music folder."""
        if _remembered.folder is not None:
            return _remembered.folder
        music = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)
        return Path(music) if music else Path.home()

    def temp_dir(self) -> Path:
        return self._temp_dir if self._temp_dir is not None else Path(tempfile.gettempdir())

    # --- Showing and phases -----------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt)
        """Each opening lists the sources again (a device may have come or gone)."""
        super().showEvent(event)
        idle = self._phase in (Phase.LOADING, Phase.READY, Phase.NO_SOURCES)
        if idle and self._monitor is None and not self._listing:
            self.load_sources()
        self._ticker.start()

    def _set_phase(self, phase: Phase) -> None:
        self._phase = phase
        idle = phase in (Phase.READY, Phase.NO_SOURCES)
        self.source_combo.setEnabled(idle and bool(self._sources))
        for option in (self.start_when_sound, self.silence_stop):
            option.setEnabled(idle)
        self.silence_seconds.setEnabled(idle and self.silence_stop.isChecked())
        self.record_button.setEnabled(phase is Phase.READY and self.selected_source() is not None)
        self.stop_button.setEnabled(phase is Phase.RECORDING)
        self.discard_button.setEnabled(phase in (Phase.RECORDING, Phase.PENDING))
        self.save_button.setVisible(phase is Phase.PENDING)
        self.progress.setVisible(phase is Phase.CONVERTING)
        if phase is not Phase.RECORDING:
            self.time_label.setStyleSheet("")
        if phase in (Phase.READY, Phase.NO_SOURCES, Phase.LOADING):
            self.time_label.setText(clock(0))
        self._refresh_free_space(force=True)

    def _show_message(self, text: str, *, error: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(ERROR_STYLE if error else "")
        self.message_label.setVisible(bool(text))

    def _show_error(self, what: str, error: BaseException) -> None:
        log_error(what, error)
        self._show_message(error_text(error), error=True)

    def _run(
        self,
        pool: QThreadPool,
        work: Callable[[], object],
        done: Callable[[object, object], None],
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """`work` in `pool`; `done(result, error)` back in this thread, unless the window was closed."""
        self._start(pool, work, self._task(done, progress))

    def _task(
        self, done: Callable[[object, object], None], progress: Callable[[int, int], None] | None = None
    ) -> int:
        """A number for a new task, whose answers go to `done` and `progress`."""
        self._last_task += 1
        self._callbacks[self._last_task] = _Callbacks(self._session, done, progress)
        return self._last_task

    def _start(self, pool: QThreadPool, work: Callable[[], object], task: int) -> None:
        self._pending_tasks += 1
        pool.start(_Task(task, work, self._bus))

    def _progress_of(self, task: int) -> Callable[[int, int], None]:
        """For the worker thread: reports the progress of `task`."""
        bus = self._bus
        return lambda done, total: bus.progress.emit(task, done, total)

    def _on_task_done(self, task: int, result: object, error: object) -> None:
        self._pending_tasks -= 1
        callbacks = self._callbacks.pop(task, None)
        if callbacks is not None and callbacks.session is self._session:
            callbacks.done(result, error)

    def _on_task_progress(self, task: int, done: int, total: int) -> None:
        callbacks = self._callbacks.get(task)
        if callbacks is not None and callbacks.progress is not None and callbacks.session is self._session:
            callbacks.progress(done, total)

    # --- Sources and monitor ----------------------------------------------------------------------

    def load_sources(self, notice: str = "") -> None:
        """list_sources() in a worker thread; then the remembered source (or the first) is monitored.

        `notice` is shown once the list is there (why it was listed again).
        """
        self._listing = True
        self._notice = notice
        self._set_phase(Phase.LOADING)
        self._show_message(self.tr("Cercant les sortides de so…"))
        backend = self.backend
        self._run(self._devices, lambda: list_sources(backend=backend), self._on_sources)

    def _on_sources(self, result: object, error: object) -> None:
        self._listing = False
        if isinstance(error, BaseException):
            self._sources = ()
            self._fill_sources()
            self._set_phase(Phase.NO_SOURCES)
            self._show_error("llista d'orígens", error)
            return
        sources = cast(tuple[object, ...], result)
        self._sources = tuple(source for source in sources if isinstance(source, AudioSource))
        if not any(source.kind is SourceKind.OUTPUT_LOOPBACK for source in self._sources):
            # §1.7 ter: without any output there is nothing to record by default, even with inputs.
            self._show_message(message(ERROR_NO_DEVICE), error=True)
        else:
            self._show_message(self._notice, error=bool(self._notice))
        self._fill_sources()
        if not self._sources:
            self._set_phase(Phase.NO_SOURCES)
            return
        self._set_phase(Phase.READY)
        self._start_monitor()

    def _fill_sources(self) -> None:
        """Two groups: "So de l'ordinador" (outputs) and "Micròfon i entrada de línia" (inputs, G6)."""
        combo = self.source_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            model = cast(QStandardItemModel, combo.model())
            groups = (
                (SourceKind.OUTPUT_LOOPBACK, self.tr("So de l'ordinador")),
                (SourceKind.INPUT, self.tr("Micròfon i entrada de línia")),
            )
            for kind, header in groups:
                members = [source for source in self._sources if source.kind is kind]
                if not members:
                    continue
                combo.addItem(header)
                model.item(combo.count() - 1).setEnabled(False)
                for source in members:
                    name = (
                        self.tr("{name} — per defecte").format(name=source.name)
                        if source.is_default
                        else source.name
                    )
                    combo.addItem("    " + name, source)
            chosen = next((s for s in self._sources if s.id == _remembered.source_id), None)
            if chosen is None:
                chosen = next(iter(self._sources), None)  # the default output (list_sources' order)
            if chosen is not None:
                self.select_source(chosen.id)
        finally:
            combo.blockSignals(False)

    def _on_source_chosen(self, index: int) -> None:
        del index
        source = self.selected_source()
        if source is None or self._phase is not Phase.READY:
            return
        _remembered.source_id = source.id
        self._show_message("")
        self._start_monitor()
        self._set_phase(Phase.READY)

    def _start_monitor(self) -> None:
        """Waves and level of the chosen source before recording (never writes anything)."""
        self._stop_monitor()
        source = self.selected_source()
        if source is None:
            return
        _remembered.source_id = source.id
        monitor = Monitor(source, backend=self.backend)
        self._monitor = monitor
        self.wave.set_channels(source.recorded_channels)
        self.wave.follow(monitor)

        def started(result: object, error: object) -> None:
            del result
            if self._monitor is not monitor:
                return
            if isinstance(error, BaseException):
                self._monitor = None
                self.wave.stop_following()
                self._show_error(f"monitor de {source.name!r}", error)

        self._run(self._devices, monitor.start, started)

    def _stop_monitor(self) -> None:
        monitor = self._monitor
        self._monitor = None
        if monitor is not None:
            self.wave.stop_following()
            self._run(self._devices, monitor.stop, lambda result, error: None)

    def _check_monitor(self) -> None:
        """The output changed or went away while monitoring: list the sources again."""
        monitor = self._monitor
        if monitor is None or monitor.error is None:
            return
        log_error(f"monitor de {monitor.source.name!r}", monitor.error)
        self._stop_monitor()
        self.load_sources(self.tr("La sortida de so ha canviat o s'ha desconnectat. Tria l'origen de nou."))

    # --- Recording --------------------------------------------------------------------------------

    def record(self) -> None:
        """[● Grava]: stops the monitor and starts a Recorder on the same source."""
        source = self.selected_source()
        if self._phase is not Phase.READY or source is None:
            return
        self._stop_monitor()
        self._show_message("")
        recorder = Recorder(source, self.temp_dir(), self.settings(), backend=self.backend)
        self._recorder = recorder
        self.wave.set_channels(source.recorded_channels)
        self._set_phase(Phase.STARTING)
        self._run(self._devices, recorder.start, self._on_started)

    def _on_started(self, result: object, error: object) -> None:
        del result
        recorder = self._recorder
        if recorder is None:
            return
        if isinstance(error, BaseException):
            self._recorder = None
            self._show_error("començar", error)
            self._back_to_ready()
            return
        self._set_phase(Phase.RECORDING)
        self.wave.follow(recorder, recording=recorder.state is RecorderState.RECORDING)
        self.tick()

    def tick(self) -> None:
        """RECORD_WAVE_REFRESH_HZ times per second: time, colours, free space and the end on its own."""
        self._ticks += 1
        if self._phase is Phase.READY:
            self._check_monitor()
        recorder = self._recorder
        if self._phase is Phase.RECORDING and recorder is not None:
            state = recorder.state
            waiting = state is RecorderState.WAITING
            self.wave.set_recording(state is RecorderState.RECORDING)
            elapsed = recorder.elapsed_s
            if waiting:
                self.time_label.setText(self.tr("Esperant que soni…"))
                self.time_label.setStyleSheet("")
            else:
                self.time_label.setText("● " + clock(elapsed))
                warn = elapsed >= recorder.settings.max_duration_s - defaults.RECORD_MAX_WARNING_S
                self.time_label.setStyleSheet(WARNING_STYLE if warn else RECORDING_STYLE)
            if state in (RecorderState.FINISHED, RecorderState.INTERRUPTED):
                self.stop()  # the automatic stop for silence, or an interruption (G1)
                return
        self._refresh_free_space()

    def time_is_warning(self) -> bool:
        return self.time_label.styleSheet() == WARNING_STYLE

    def _refresh_free_space(self, *, force: bool = False) -> None:
        now = self._ticks / defaults.RECORD_WAVE_REFRESH_HZ
        if not force and now - self._last_free_check < FREE_SPACE_EVERY_S:
            return
        self._last_free_check = now
        try:
            free = self.free_space(self.temp_dir())
        except OSError:
            self.free_label.setText("")
            return
        self.free_label.setText(self.tr("Lliure: {size}").format(size=gigabytes(free)))

    def stop(self) -> None:
        """[■ Atura], the automatic stop or an interruption: Recorder.stop() in a worker thread."""
        recorder = self._recorder
        if self._phase is not Phase.RECORDING or recorder is None:
            return
        self._set_phase(Phase.STOPPING)
        self.wave.stop_following()
        session = self._session

        def work() -> RecordingResult:
            result = recorder.stop()
            if session.abandoned.is_set():
                result.wav_path.unlink(missing_ok=True)
                raise CancelledError
            return result

        self._run(self._devices, work, self._on_stopped)

    def _on_stopped(self, result: object, error: object) -> None:
        recorder = self._recorder
        self._recorder = None
        if isinstance(error, BaseException) or not isinstance(result, RecordingResult):
            self.wave.clear()
            self._show_error("aturar", error if isinstance(error, BaseException) else RuntimeError(result))
            self._back_to_ready()
            return
        self._result = result
        if recorder is not None:
            total = result.duration_s + result.trimmed_start_s + result.trimmed_end_s
            self.wave.show_overview(
                recorder.overview(self.wave.wave_width()), result.trimmed_start_s, result.trimmed_end_s, total
            )
        self.time_label.setText(clock(result.duration_s))
        self._set_phase(Phase.PENDING)
        self.save_pending()

    # --- Saving -----------------------------------------------------------------------------------

    def save_pending(self) -> None:
        """Asks the folder and the name (every time, the last folder proposed), then converts to MP3."""
        result = self._result
        if self._phase is not Phase.PENDING or result is None:
            return
        fallback = self.tr("Gravació")
        suggested = safe_target_path(self.suggested_folder(), self.suggested_name(), fallback=fallback)
        chosen = self.questions.choose_recording_path(suggested)
        if chosen is None:
            self._show_message(self.tr("La gravació encara no s'ha desat: prem «Desa…» o «Descarta»."))
            return
        _remembered.folder = chosen.parent
        title = song_title(chosen)
        target = safe_target_path(chosen.parent, title, fallback=fallback)
        self._set_phase(Phase.CONVERTING)
        self.progress.setValue(0)
        self._show_message(self.tr("Convertint a MP3…"))
        session, convert = self._session, self._convert
        task = self._task(self._on_saved, self._on_progress)
        progress = self._progress_of(task)

        def work() -> Path:
            saved = False
            try:
                convert(
                    result.wav_path,
                    target,
                    defaults.RECORD_MP3_BITRATE_KBPS,
                    Mp3Tags(title=target.stem),
                    progress,
                    session.cancel,
                )
                saved = target.is_file() and not session.cancel.cancelled
                if not saved:
                    raise CancelledError  # convert_to_mp3 returns without a file only when cancelled
                return target
            finally:
                # The WAV goes once saved, or with the window; a failed conversion keeps it to retry.
                if saved or session.abandoned.is_set():
                    result.wav_path.unlink(missing_ok=True)

        self._start(self._conversions, work, task)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(min(PROGRESS_STEPS, round(PROGRESS_STEPS * done / total)))

    def _on_saved(self, result: object, error: object) -> None:
        if isinstance(result, Path):
            self._result = None
            self.saved.append(result)
            self._show_message(self.tr("Desada: {name}").format(name=result.name))
            if self.add_to_project.isChecked():
                self._add_songs([result])
            self._back_to_ready()
            return
        self._set_phase(Phase.PENDING)
        if isinstance(error, BaseException) and not isinstance(error, CancelledError):
            self._show_error("convertir", error)

    # --- Discarding and closing -------------------------------------------------------------------

    def discard(self) -> None:
        """[Descarta]: deletes the recording unsaved (asks if longer than RECORD_DISCARD_CONFIRM_S)."""
        recorder, result = self._recorder, self._result
        if self._phase is Phase.RECORDING and recorder is not None:
            length = recorder.elapsed_s
        elif self._phase is Phase.PENDING and result is not None:
            length = result.duration_s
        else:
            return
        if length > defaults.RECORD_DISCARD_CONFIRM_S and not self.questions.confirm_discard_recording():
            return
        self._recorder = None
        self._result = None
        self._set_phase(Phase.DISCARDING)
        self.wave.stop_following()
        self.wave.clear()
        self._run(self._devices, _discarding(recorder, result), self._on_discarded)

    def _on_discarded(self, result: object, error: object) -> None:
        del result
        if isinstance(error, BaseException):
            log_error("descartar", error)
        self._show_message(self.tr("S'ha descartat la gravació."))
        self._back_to_ready()

    def _back_to_ready(self) -> None:
        """After a recording (saved, discarded or interrupted): the monitor again; the message stays."""
        self._set_phase(Phase.READY if self._sources else Phase.NO_SOURCES)
        if self._sources:
            self._start_monitor()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt)
        """With a recording: asks "La gravació s'esborrarà…" and, if confirmed, deletes it (G1)."""
        if self._phase in HOLDS_A_RECORDING and not self.questions.confirm_close_recording():
            event.ignore()
            return
        self.shut_down()
        super().closeEvent(event)

    def shut_down(self) -> None:
        """Ends everything and waits until the temporary files are gone (no file is left, G1)."""
        session = self._session
        session.abandoned.set()
        session.cancel.cancel()
        self._session = _Session()
        self._ticker.stop()
        recorder, result = self._recorder, self._result
        self._recorder = None
        self._result = None
        monitor = self._monitor
        self._monitor = None
        self.wave.stop_following()
        self.wave.clear()
        if monitor is not None:
            self._devices.start(_Task(0, monitor.stop, None))
        if recorder is not None or result is not None:
            self._devices.start(_Task(0, _discarding(recorder, result), None))
        self.wait_for_work()
        self._listing = False
        self._sources = ()
        self._fill_sources()
        self._show_message("")
        self._set_phase(Phase.LOADING)


def _discarding(recorder: Recorder | None, result: RecordingResult | None) -> Callable[[], None]:
    """The work of deleting a recording in progress or kept: Recorder.discard() waits for its thread."""

    def work() -> None:
        if recorder is not None:
            recorder.discard()
        if result is not None:
            result.wav_path.unlink(missing_ok=True)

    return work
