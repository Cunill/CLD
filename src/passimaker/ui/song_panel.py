"""Song panel: the settings of the song selected in the music strip (§1.7).

Fade in and fade out (a check box and the seconds), the trim ("Comença a" and "Acaba a", with the
waveform bar and its two handles), [Escoltar el tros] and the volume. Every control sends an
UpdateSong to the controller (rule 2); the controls follow the project, so undo moves them too.

Listening plays only the chosen part of the song, mixed exactly as in the show (volume,
levelling, fades and master volume), with the mixer of passimaker.audio: ``SongListening``
prepares it and opens the sound device in a worker thread (both can take longer than 50 ms).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace
from typing import cast

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from passimaker.audio import SAMPLE_RATE, AudioSource, MixedAudioSource, prepare
from passimaker.common import PassiMakerError
from passimaker.export import cache_root
from passimaker.i18n import message
from passimaker.model import Change, Fade, Project, ProjectController, Song, defaults
from passimaker.model.commands import UpdateSong
from passimaker.model.editing import song_duration
from passimaker.preview import AudioOutput, SoundDeviceOutput
from passimaker.timeline import build_audio_plan
from passimaker.ui.formatting import clock
from passimaker.ui.music_strip import MISSING_COLOUR
from passimaker.ui.project_panel import PERCENT, number_box, percent_box, seconds_box
from passimaker.ui.trim_bar import TRIM_STEP_S, Peaks, TrimBar, WaveformLoader, limit_trim

type OutputFactory = Callable[[], AudioOutput]

_log = logging.getLogger(__name__)

LISTEN_END_MARGIN_MS = 150
"""After the part has been heard, the device is stopped a little later (its own latency)."""


def listening_source(project: Project, song: Song) -> MixedAudioSource:
    """The chosen part of the song alone, mixed as in the show; it lasts exactly that part.

    The plan is the one the show would have if the song were the only one and the show lasted as
    long as it (no final fade). The mix of a project is as long as its video, so the length is set
    afterwards. Raises PassiMakerError if the song cannot be read.
    """
    length = song_duration(song)
    alone = replace(project, photos=(), music=replace(project.music, songs=(song,)))
    plan = build_audio_plan((song,), length, defaults.FPS)
    mixed = prepare(alone, plan, cache_root() / "audio")
    failure = mixed.failures.get(song.id)
    if failure is not None:
        raise failure
    return replace(mixed, total_frames=round(length * SAMPLE_RATE))


class _ListenSignals(QObject):
    started = Signal(int, float)
    failed = Signal(int, str)


class _Job(QRunnable):
    def __init__(self, work: Callable[[], None]) -> None:
        super().__init__()
        self._work = work

    def run(self) -> None:
        self._work()


class SongListening(QObject):
    """[Escoltar el tros]: plays the trimmed part of one song once, or stops it."""

    started = Signal()
    stopped = Signal()
    failed = Signal(str)
    """Catalan text of the reason the song cannot be heard."""

    def __init__(
        self,
        output_factory: OutputFactory = SoundDeviceOutput,
        source_factory: Callable[[Project, Song], AudioSource] = listening_source,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.output_factory = output_factory
        self._source_factory = source_factory
        self._output: AudioOutput | None = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)  # starting and stopping the device never overlap
        self._generation = 0
        self._song_id: str | None = None
        self._signals = _ListenSignals(self)
        self._signals.started.connect(self._on_started)
        self._signals.failed.connect(self._on_failed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.stop)

    @property
    def song_id(self) -> str | None:
        """The song being prepared or heard, or None."""
        return self._song_id

    def play(self, project: Project, song: Song) -> None:
        self.stop()
        self._generation += 1
        generation = self._generation
        self._song_id = song.id

        def work() -> None:
            try:
                source = self._source_factory(project, song)
                if generation != self._generation:
                    return  # stopped (or another song) while it was being prepared: not a sound
                if self._output is None:
                    self._output = self.output_factory()
                self._output.start(source, 0.0)
            except PassiMakerError as error:
                self._signals.failed.emit(generation, message(error.message_key))
                return
            except Exception:
                # No sound device, no PortAudio, a cache folder that cannot be written...
                _log.exception("Could not play the part of the song")
                self._signals.failed.emit(generation, "")
                return
            self._signals.started.emit(generation, source.duration_s)

        self._pool.start(_Job(work))

    def stop(self) -> None:
        if self._song_id is None:
            return
        self._generation += 1
        self._song_id = None
        self._timer.stop()
        # Queued after the job that may still be starting the sound (one thread), so it stops it too.
        self._pool.start(_Job(self._stop_output))
        self.stopped.emit()

    def wait(self, milliseconds: int = 10_000) -> bool:
        return self._pool.waitForDone(milliseconds)

    def close(self) -> None:
        """Stops and closes the sound device (stop() alone keeps it open for a while: M04)."""
        self.stop()
        self.wait()
        if isinstance(self._output, SoundDeviceOutput):
            self._output.close()

    def _stop_output(self) -> None:
        if self._output is not None:
            self._output.stop()

    def _on_started(self, generation: int, duration_s: float) -> None:
        if generation != self._generation:  # stopped (or another song) while it was being prepared
            return
        self._timer.start(round(duration_s * 1000) + LISTEN_END_MARGIN_MS)
        self.started.emit()

    def _on_failed(self, generation: int, text: str) -> None:
        if generation != self._generation:
            return
        self._song_id = None
        self.failed.emit(text or self.tr("no s'ha pogut obrir el dispositiu de so."))
        self.stopped.emit()


class SongPanel(QWidget):
    """The properties of the song selected in the music strip."""

    listening_started = Signal()
    """The window pauses the preview: two sounds at once would be confusing."""

    def __init__(
        self,
        controller: ProjectController,
        waveforms: WaveformLoader | None = None,
        listening: SongListening | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._song_id: str | None = None
        self._updating = False
        self.waveforms = waveforms if waveforms is not None else WaveformLoader(parent=self)
        self.listening = listening if listening is not None else SongListening(parent=self)
        self._missing: frozenset[str] = frozenset()

        in_seconds = self.tr(" s")
        self.title = QLabel()
        self.length = QLabel()
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet(f"color: {MISSING_COLOUR.name()};")
        self.fade_in_enabled = QCheckBox(self.tr("Fosa d'entrada"))
        self.fade_in = seconds_box(defaults.SONG_FADE_RANGE, in_seconds)
        self.fade_out_enabled = QCheckBox(self.tr("Fosa de sortida"))
        self.fade_out = seconds_box(defaults.SONG_FADE_RANGE, in_seconds)
        self.trim_bar = TrimBar()
        self.trim_start = self._trim_box(in_seconds)
        self.trim_end = self._trim_box(in_seconds)
        self.listen = QPushButton()
        self.volume = percent_box(defaults.SONG_VOLUME_RANGE, self.tr(" %"))

        self.fade_in_enabled.setToolTip(self.tr("La cançó comença baixet i puja fins al volum normal"))
        self.fade_out_enabled.setToolTip(self.tr("La cançó s'apaga a poc a poc en lloc de tallar-se"))
        self.trim_start.setToolTip(self.tr("D'on comença a sonar la cançó"))
        self.trim_end.setToolTip(self.tr("On deixa de sonar la cançó"))
        self.listen.setToolTip(self.tr("Escolta el tros triat tal com sonarà al vídeo"))
        self.volume.setToolTip(self.tr("Volum d'aquesta cançó respecte de les altres"))

        fades = QFormLayout()
        fades.addRow(self.fade_in_enabled, self.fade_in)
        fades.addRow(self.fade_out_enabled, self.fade_out)
        trim = QFormLayout()
        trim.addRow(self.tr("Comença a"), self.trim_start)
        trim.addRow(self.tr("Acaba a"), self.trim_end)
        trim.addRow("", self.listen)
        trim.addRow(self.tr("Volum"), self.volume)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.length)
        layout.addWidget(self.problem)
        layout.addLayout(fades)
        layout.addWidget(QLabel(self.tr("Retall")))
        layout.addWidget(self.trim_bar)
        layout.addLayout(trim)
        layout.addStretch(1)

        self.fade_in_enabled.toggled.connect(self._on_fades)
        self.fade_in.valueChanged.connect(self._on_fades)
        self.fade_out_enabled.toggled.connect(self._on_fades)
        self.fade_out.valueChanged.connect(self._on_fades)
        self.trim_start.valueChanged.connect(self._on_trim_boxes)
        self.trim_end.valueChanged.connect(self._on_trim_boxes)
        self.trim_bar.trim_moving.connect(self._show_trim)
        self.trim_bar.trim_changed.connect(self._send_trim)
        self.volume.valueChanged.connect(self._on_volume)
        self.listen.clicked.connect(self._on_listen)
        self.waveforms.ready.connect(self._on_waveform)
        self.listening.started.connect(self._refresh_listen)
        self.listening.started.connect(self.listening_started)
        self.listening.stopped.connect(self._refresh_listen)
        self.listening.failed.connect(self._on_listen_failed)

        self._unsubscribe = controller.subscribe(self._on_changes)
        self.refresh()

    def _trim_box(self, suffix: str) -> QDoubleSpinBox:
        box = number_box()
        box.setDecimals(1)
        box.setSingleStep(TRIM_STEP_S)
        box.setSuffix(suffix)
        return box

    # --- Selection ---------------------------------------------------------------------------------

    def show_song(self, song_id: str | None) -> None:
        if song_id != self._song_id:
            self.listening.stop()
            self.problem.clear()
        self._song_id = song_id
        song = self.song()
        if song is not None:
            known = self.waveforms.known(song.path)
            if known is not None and known[1]:
                self.waveforms.forget(song.path)  # it failed before: the file may be readable now
            self.trim_bar.set_peaks(None, self.tr("Llegint la forma d'ona…"))
            self.waveforms.request(song.path)
        self.refresh()

    def set_missing(self, ids: frozenset[str]) -> None:
        """Songs whose file is not found (§1.7: marked in red, they cannot be heard)."""
        found_again = (
            self._song_id is not None and self._song_id in self._missing and self._song_id not in ids
        )
        self._missing = ids
        if found_again:
            self.problem.clear()
            self.show_song(self._song_id)  # reads the waveform again
            return
        self.refresh()

    def song(self) -> Song | None:
        for song in self._controller.project.music.songs:
            if song.id == self._song_id:
                return song
        return None

    # --- From the project to the controls ---------------------------------------------------------

    def refresh(self) -> None:
        song = self.song()
        if song is None and self._song_id is not None:
            # The song is gone (deleted, or an undo): it must not go on sounding.
            if self.listening.song_id == self._song_id:
                self.listening.stop()
            self.problem.clear()
            self._song_id = None
        self.setEnabled(song is not None)
        with self._quiet():
            if song is None:
                self.title.setText(self.tr("Cap cançó seleccionada"))
                self.length.clear()
                self.trim_bar.set_song(0.0, 0.0, 0.0)
            else:
                self._show_song(song)
        self._refresh_listen()

    def _show_song(self, song: Song) -> None:
        number = [s.id for s in self._controller.project.music.songs].index(song.id) + 1
        self.title.setText(self.tr("Cançó {number} · {name}").format(number=number, name=song.path.name))
        self.length.setText(
            self.tr("Dura {length} (de {original})").format(
                length=clock(song_duration(song)), original=clock(song.original_duration_s)
            )
        )
        if song.id in self._missing:
            self.problem.setText(self.tr("No es troba el fitxer d'aquesta cançó."))
        self.fade_in_enabled.setChecked(song.fade_in.enabled)
        self.fade_in.setValue(song.fade_in.seconds)
        self.fade_in.setEnabled(song.fade_in.enabled)
        self.fade_out_enabled.setChecked(song.fade_out.enabled)
        self.fade_out.setValue(song.fade_out.seconds)
        self.fade_out.setEnabled(song.fade_out.enabled)
        start, end = trim_of(song)
        self.trim_bar.set_song(song.original_duration_s, start, end)
        self._show_trim(start, end)
        self.volume.setValue(round(song.volume * PERCENT))

    def _show_trim(self, start: float, end: float) -> None:
        """The two boxes follow the handles; each box's range keeps the start before the end."""
        with self._quiet():
            duration = self.trim_bar.duration
            self.trim_start.setRange(0.0, max(0.0, end - TRIM_STEP_S))
            self.trim_end.setRange(min(duration, start + TRIM_STEP_S), duration)
            self.trim_start.setValue(start)
            self.trim_end.setValue(end)

    def _refresh_listen(self) -> None:
        song = self.song()
        playing = song is not None and self.listening.song_id == song.id
        self.listen.setText(self.tr("■ Aturar") if playing else self.tr("▶ Escoltar el tros"))
        self.listen.setEnabled(song is not None and song.id not in self._missing)

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if Change.MUSIC in changes:
            self.refresh()

    def _on_waveform(self, path: object, peaks: object, error: str) -> None:
        song = self.song()
        if song is None or path != song.path:
            return
        if error:
            # §1.7: a song that cannot be read is marked in red, with the reason.
            self.trim_bar.set_peaks(None)
            self.problem.setText(
                self.tr("No es pot llegir aquesta cançó: {reason}").format(reason=message(error))
            )
        elif isinstance(peaks, np.ndarray):
            self.trim_bar.set_peaks(cast(Peaks, peaks))

    @contextmanager
    def _quiet(self) -> Generator[None]:
        previous = self._updating
        self._updating = True
        try:
            yield
        finally:
            self._updating = previous

    # --- From the controls to the controller ------------------------------------------------------

    def _on_fades(self, *_args: object) -> None:
        song = self.song()
        if song is None or self._updating:
            return
        self.fade_in.setEnabled(self.fade_in_enabled.isChecked())
        self.fade_out.setEnabled(self.fade_out_enabled.isChecked())
        self._send(
            replace(
                song,
                fade_in=Fade(self.fade_in_enabled.isChecked(), _kept(self.fade_in, song.fade_in.seconds)),
                fade_out=Fade(self.fade_out_enabled.isChecked(), _kept(self.fade_out, song.fade_out.seconds)),
            )
        )

    def _on_trim_boxes(self, *_args: object) -> None:
        song = self.song()
        if song is None or self._updating:
            return
        start, end = trim_of(song)
        self._send_trim(_kept(self.trim_start, start), _kept(self.trim_end, end))

    def _send_trim(self, start: float, end: float) -> None:
        song = self.song()
        if song is None:
            return
        start, end = limit_trim(start, end, song.original_duration_s)
        whole = end >= song.original_duration_s - TRIM_STEP_S / 2
        self._send(replace(song, trim_start_s=start, trim_end_s=None if whole else end))

    def _on_volume(self, percent: float) -> None:
        song = self.song()
        if song is not None:
            self._send(replace(song, volume=percent / PERCENT))

    def _send(self, song: Song) -> None:
        if not self._updating and song != self.song():
            self._controller.execute(UpdateSong(song))

    def _on_listen(self) -> None:
        song = self.song()
        if song is None:
            return
        if self.listening.song_id == song.id:
            self.listening.stop()
        else:
            self.listening.play(self._controller.project, song)
        self._refresh_listen()

    def _on_listen_failed(self, text: str) -> None:
        self.problem.setText(self.tr("No es pot escoltar aquesta cançó: {reason}").format(reason=text))

    def close_panel(self) -> None:
        self._unsubscribe()
        self.listening.close()
        self.waveforms.wait()


def _kept(box: QDoubleSpinBox, current: float) -> float:
    """The box's value, or the song's own if the box only shows it rounded (the user did not touch it).

    Editing one control must not round the values of the others (a trim of 120,25 s stays 120,25 s).
    """
    half_step = 0.5 * 10 ** -box.decimals()
    return current if abs(box.value() - current) <= half_step + 1e-9 else box.value()


def trim_of(song: Song) -> tuple[float, float]:
    """(start, end) of the part that is played, in seconds of the file."""
    end = song.original_duration_s if song.trim_end_s is None else song.trim_end_s
    return limit_trim(song.trim_start_s, end, song.original_duration_s)
