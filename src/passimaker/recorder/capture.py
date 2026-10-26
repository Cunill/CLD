"""Recorder (records to a temporary WAV) and Monitor (waves and level only), block C09.

Both capture in their own thread, which opens the source, reads it and closes it (COM lives in
that thread, block C08); every property and peaks_since() can be read from another thread (the
interface reads them RECORD_WAVE_REFRESH_HZ times per second). Recorder.stop() trims and
normalises the WAV, which takes a while for a long recording: call it outside the UI thread.
"""

from __future__ import annotations

import errno
import logging
import math
import shutil
import threading
from collections import deque
from pathlib import Path

import numpy as np

from passimaker.model import defaults
from passimaker.recorder.backend import CaptureBackend, CaptureStream
from passimaker.recorder.devices import default_backend
from passimaker.recorder.peaks import PeakBuffer, frames_per_column, reduce_columns
from passimaker.recorder.silence import amplitude_to_dbfs, dbfs_to_amplitude, normalize_gain, trim_silence
from passimaker.recorder.types import (
    ERROR_NO_SPACE,
    AudioFrames,
    AudioSource,
    PeakColumns,
    RecorderDeviceError,
    RecorderDeviceLostError,
    RecorderDiskFullError,
    RecorderError,
    RecorderMaxDurationError,
    RecorderSilentError,
    RecorderState,
    RecordingResult,
    RecordingSettings,
    SourceKind,
    StopReason,
)
from passimaker.recorder.wavwriter import TempWav, read_frames

_log = logging.getLogger(__name__)

_READ_TIMEOUT_S = 0.2
_JOIN_TIMEOUT_S = 5.0
"""How long stop() and discard() wait for the capture thread (a hung driver must not hang the UI)."""
_COPY_FRAMES = 1 << 16
"""Frames copied at a time when stop() trims or normalises the WAV."""
_DISK_FULL_ERRNOS = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


def free_bytes(folder: Path) -> int:
    """Free space where the temporary WAV goes (the tests replace it)."""
    return shutil.disk_usage(folder).free


class _Capture:
    """The capture thread shared by Monitor and Recorder.

    The thread opens the source, feeds every block to the live waves and the level, checks the
    default output every RECORD_DEVICE_POLL_S of audio (WASAPI does not report a change, block
    C08) and hands the block to _on_block(); it closes the source when it ends.
    """

    def __init__(self, source: AudioSource, backend: CaptureBackend | None, columns_per_s: int) -> None:
        self._source = source
        self._backend = backend or default_backend()
        self._columns_per_s = columns_per_s
        self._lock = threading.Lock()
        self._halt_event = threading.Event()
        self._opened = threading.Event()
        self._thread: threading.Thread | None = None
        self._open_error: RecorderError | None = None
        self._error: RecorderError | None = None
        self._sample_rate = 0
        self._live: PeakBuffer | None = None
        self._level: tuple[float, ...] = (-math.inf,) * source.recorded_channels

    @property
    def source(self) -> AudioSource:
        return self._source

    @property
    def level_dbfs(self) -> tuple[float, ...]:
        """Current peak level of each recorded channel, in dBFS (-inf for digital silence)."""
        with self._lock:
            return self._level

    def peaks_since(self, index: int) -> tuple[PeakColumns, int]:
        """The columns after `index` (0 the first time) and the new index to pass next time.

        Only the last RECORD_WAVE_WINDOW_S are kept: if `index` is older, the columns start there.
        """
        with self._lock:
            if self._live is None:
                return np.zeros((0, self._source.recorded_channels, 2), dtype=np.float32), max(0, index)
            return self._live.since(index)

    @property
    def error(self) -> RecorderError | None:
        with self._lock:
            return self._error

    # --- capture thread ---------------------------------------------------------------------------------

    def _launch(self, name: str) -> None:
        """Start the thread and wait until the source is open; raises what opening it raised."""
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()
        if not self._opened.wait(defaults.RECORD_OPEN_TIMEOUT_S):
            self._halt_event.set()
            raise RecorderDeviceError(f"the sound system took more than {defaults.RECORD_OPEN_TIMEOUT_S:g} s")
        if self._open_error is not None:
            self._thread.join(_JOIN_TIMEOUT_S)
            raise self._open_error

    def _run(self) -> None:
        try:
            stream = self._backend.open(self._source)
        except BaseException as error:
            self._open_error = _as_recorder_error(error)
            self._opened.set()
            return
        failed = True
        try:
            try:
                self._prepare(stream)
            except BaseException as error:
                self._open_error = _as_recorder_error(error)
                return
            finally:
                self._opened.set()
            failed = not self._capture(stream)
        finally:
            stream.close()
            self._ended(failed)
            _log.info(
                "Capture of %r ended: %d data discontinuities", self._source.name, stream.discontinuities()
            )

    def _prepare(self, stream: CaptureStream) -> None:
        self._sample_rate = stream.sample_rate
        column = frames_per_column(stream.sample_rate, self._columns_per_s)
        window = max(1, round(defaults.RECORD_WAVE_WINDOW_S * stream.sample_rate / column))
        with self._lock:
            self._live = PeakBuffer(self._source.recorded_channels, column, window)

    def _capture(self, stream: CaptureStream) -> bool:
        """Read until halted or _on_block() says it has finished; False if it failed (error set)."""
        watched = self._watched_output()
        poll_frames = max(1, round(defaults.RECORD_DEVICE_POLL_S * stream.sample_rate))
        received = 0
        next_poll = poll_frames
        try:
            while not self._halt_event.is_set():
                block = stream.read(_READ_TIMEOUT_S)
                if block is None or block.shape[0] == 0:
                    continue
                block = _fit_channels(block, self._source.recorded_channels)
                received += block.shape[0]
                level = tuple(amplitude_to_dbfs(float(peak)) for peak in np.abs(block).max(axis=0))
                with self._lock:
                    assert self._live is not None
                    self._live.add(block)
                    self._level = level
                if received >= next_poll:
                    next_poll += poll_frames
                    self._poll(watched)
                if not self._on_block(block):
                    break
        except BaseException as error:
            self._fail(_as_recorder_error(error))
            return False
        return True

    def _watched_output(self) -> str | None:
        """The output whose replacement as default means the sound went elsewhere (block C08)."""
        if self._source.kind is not SourceKind.OUTPUT_LOOPBACK:
            return None
        default = self._backend.default_output_id()
        return self._source.id if default == self._source.id else None

    def _poll(self, watched: str | None) -> None:
        if watched is None:
            return
        now = self._backend.default_output_id()
        if now != watched:
            raise RecorderDeviceLostError(f"the default output changed: {watched} → {now}")

    def _fail(self, error: RecorderError) -> None:
        """Delete what was written, then make the error visible (decision 0013, G1)."""
        self._delete_files()
        _log.warning("Capture of %r interrupted: %s", self._source.name, error)
        with self._lock:
            self._error = error
            self._interrupted()

    def _halt(self) -> bool:
        """Ask the thread to end and wait for it; False if it did not end in time."""
        self._halt_event.set()
        thread = self._thread
        if thread is None or thread is threading.current_thread():
            return True
        thread.join(_JOIN_TIMEOUT_S)
        return not thread.is_alive()

    # --- hooks ------------------------------------------------------------------------------------------

    def _on_block(self, block: AudioFrames) -> bool:
        """Called in the thread for every block; False to end the capture normally."""
        del block
        return True

    def _ended(self, failed: bool) -> None:
        """Called in the thread when it ends (after closing the source)."""
        del failed

    def _delete_files(self) -> None:
        """Called in the thread on a failure, before the error is visible."""

    def _interrupted(self) -> None:
        """Called with the lock held after a failure."""


class Monitor(_Capture):
    """Shows whether sound arrives from `source`, before recording: never writes to disk."""

    def __init__(self, source: AudioSource, *, backend: CaptureBackend | None = None) -> None:
        super().__init__(source, backend, defaults.RECORD_PEAK_COLUMNS_PER_S)
        self._started = False

    def start(self) -> None:
        """Open the source; RecorderNoDeviceError or RecorderDeviceError if it cannot."""
        if self._started:
            raise RuntimeError("Monitor.start() called twice")
        self._started = True
        self._launch("passimaker-monitor")

    def stop(self) -> None:
        """Close the source; does nothing if not started or already stopped."""
        self._halt()


class Recorder(_Capture):
    """One recording of `source` to a temporary WAV inside `temp_dir`.

    A recording is saved only when it ends by stop() (StopReason.USER) or by the automatic stop
    for silence (StopReason.SILENCE). Every other end (device lost, disk full, maximum duration,
    sound system error, discard(), closing the program) deletes the WAV (decision 0013, G1, G5).
    """

    def __init__(
        self,
        source: AudioSource,
        temp_dir: Path,
        settings: RecordingSettings | None = None,
        *,
        backend: CaptureBackend | None = None,
    ) -> None:
        self._settings = settings or RecordingSettings()
        super().__init__(source, backend, self._settings.peak_columns_per_s)
        self._temp_dir = temp_dir
        self._state = RecorderState.IDLE
        self._discarding = False
        self._wav: TempWav | None = None
        self._recorded: PeakBuffer | None = None
        self._written = 0
        self._preroll: deque[AudioFrames] = deque()
        self._preroll_frames = 0
        self._heard = False
        self._silent_frames = 0

    @property
    def settings(self) -> RecordingSettings:
        return self._settings

    @property
    def state(self) -> RecorderState:
        with self._lock:
            return self._state

    @property
    def error(self) -> RecorderError | None:
        """Why it was INTERRUPTED (the WAV is already deleted); None otherwise."""
        return super().error

    @property
    def elapsed_s(self) -> float:
        """Seconds saved so far (0 while WAITING)."""
        with self._lock:
            return self._written / self._sample_rate if self._sample_rate else 0.0

    def peaks_since(self, index: int) -> tuple[PeakColumns, int]:
        """The columns after `index` (0 the first time) and the new index; also while WAITING."""
        return super().peaks_since(index)

    def overview(self, width: int) -> PeakColumns:
        """The waves of the whole recording reduced to `width` columns (after stopping, §1.7 ter).

        Before trimming and normalising: RecordingResult says what was trimmed and the gain.
        """
        with self._lock:
            columns = (
                self._recorded.all()
                if self._recorded is not None
                else np.zeros((0, self._source.recorded_channels, 2), dtype=np.float32)
            )
        return reduce_columns(columns, width)

    def start(self) -> None:
        """Begin (WAITING with "Comença quan soni", otherwise RECORDING).

        RecorderDiskFullError(ERROR_NO_SPACE) with less than settings.min_free_bytes free;
        RecorderNoDeviceError or RecorderDeviceError if the source cannot be opened.
        """
        with self._lock:
            if self._state is not RecorderState.IDLE:
                raise RuntimeError(f"Recorder.start() in state {self._state}")
        try:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            free = free_bytes(self._temp_dir)
        except OSError as error:
            self._close_state()
            raise RecorderDeviceError(f"temporary folder {self._temp_dir}: {error}") from error
        if free < self._settings.min_free_bytes:
            self._close_state()
            raise RecorderDiskFullError(ERROR_NO_SPACE, f"{free} bytes free in {self._temp_dir}")
        try:
            self._launch("passimaker-recorder")
        except BaseException:
            self._discarding = True
            if self._halt():
                self._delete_files()
            self._close_state()
            raise

    def stop(self) -> RecordingResult:
        """End and keep the recording: trims the silence (if settings.trim) and returns the WAV.

        Raises the interruption error (Recorder.error) if it was INTERRUPTED, and
        RecorderSilentError, deleting the WAV, if no sound was recorded.
        """
        with self._lock:
            if self._state in (RecorderState.IDLE, RecorderState.CLOSED):
                raise RuntimeError(f"Recorder.stop() in state {self._state}")
        try:
            if not self._halt():
                self._discarding = True  # the thread deletes the WAV when it ends
                raise RecorderDeviceError("the capture thread did not stop")
            with self._lock:
                state, error = self._state, self._error
            if state is RecorderState.INTERRUPTED:
                assert error is not None
                raise error
            reason = StopReason.SILENCE if state is RecorderState.FINISHED else StopReason.USER
            try:
                return self._finish(reason)
            except BaseException:
                self._delete_files()
                raise
        finally:
            self._close_state()

    def discard(self) -> None:
        """End and delete everything ([Descarta], closing the window or the program)."""
        with self._lock:
            if self._state is RecorderState.CLOSED:
                return
            self._discarding = True
        if self._halt():
            self._delete_files()
        self._close_state()

    # --- capture thread ---------------------------------------------------------------------------------

    def _prepare(self, stream: CaptureStream) -> None:
        super()._prepare(stream)
        try:
            wav = TempWav(self._temp_dir, stream.sample_rate, self._source.recorded_channels)
        except OSError as error:
            raise _write_error(error) from error
        column = frames_per_column(stream.sample_rate, self._settings.peak_columns_per_s)
        with self._lock:
            self._wav = wav
            self._recorded = PeakBuffer(self._source.recorded_channels, column)
            self._state = (
                RecorderState.WAITING if self._settings.start_when_sound else RecorderState.RECORDING
            )

    def _poll(self, watched: str | None) -> None:
        super()._poll(watched)
        if free_bytes(self._temp_dir) < self._settings.min_free_bytes:
            raise RecorderDiskFullError(detail=f"less than {self._settings.min_free_bytes} bytes free")

    def _on_block(self, block: AudioFrames) -> bool:
        if self.state is RecorderState.WAITING:
            if not _any_at_or_above(block, self._settings.start_threshold_dbfs):
                self._keep_preroll(block)
                return True
            # The margin trimming keeps before the first sound comes from the audio before it.
            while self._preroll:
                self._write(self._preroll.popleft())
            self._preroll_frames = 0
            with self._lock:
                self._state = RecorderState.RECORDING
        return self._write(block)

    def _keep_preroll(self, block: AudioFrames) -> None:
        self._preroll.append(block)
        self._preroll_frames += block.shape[0]
        keep = round(self._settings.trim_margin_s * self._sample_rate)
        while self._preroll and self._preroll_frames - self._preroll[0].shape[0] >= keep:
            self._preroll_frames -= self._preroll.popleft().shape[0]

    def _write(self, block: AudioFrames) -> bool:
        """Write a block; False when the automatic stop for silence ends the recording."""
        assert self._wav is not None and self._recorded is not None
        try:
            self._wav.write(block)
        except OSError as error:
            raise _write_error(error) from error
        with self._lock:
            self._recorded.add(block)
            self._written += block.shape[0]
            written = self._written
        if written >= self._settings.max_duration_s * self._sample_rate:
            raise RecorderMaxDurationError(f"{self._settings.max_duration_s:g} s")
        loud = np.flatnonzero(_frame_peaks(block) >= dbfs_to_amplitude(self._settings.silence_threshold_dbfs))
        if loud.size:
            self._heard = True
            self._silent_frames = block.shape[0] - 1 - int(loud[-1])
        else:
            self._silent_frames += block.shape[0]
        return not (
            self._settings.silence_stop
            and self._heard
            and self._silent_frames >= self._settings.silence_stop_s * self._sample_rate
        )

    def _ended(self, failed: bool) -> None:
        if failed:
            return
        with self._lock:
            if self._recorded is not None:
                self._recorded.flush()
            discarding = self._discarding
        if discarding:
            self._delete_files()
            return
        try:
            if self._wav is not None:
                self._wav.close()
        except OSError as error:
            self._fail(_write_error(error))
            return
        with self._lock:
            if self._state is RecorderState.RECORDING and not self._halt_event.is_set():
                self._state = RecorderState.FINISHED

    def _delete_files(self) -> None:
        with self._lock:
            wav = self._wav
        if wav is not None:
            wav.delete()

    def _interrupted(self) -> None:
        self._state = RecorderState.INTERRUPTED

    def _close_state(self) -> None:
        with self._lock:
            self._state = RecorderState.CLOSED

    # --- saving -----------------------------------------------------------------------------------------

    def _finish(self, reason: StopReason) -> RecordingResult:
        """Trim and normalise the closed WAV (decision of the user of 26/10/2026)."""
        with self._lock:
            wav, recorded = self._wav, self._recorded
        if wav is None or recorded is None or wav.frames == 0:
            raise RecorderSilentError("nothing was recorded")
        rate, total = wav.sample_rate, wav.frames
        envelope = np.abs(recorded.all()).max(axis=2)
        column = recorded.frames_per_column
        columns_per_s = rate / column
        if trim_silence(envelope, columns_per_s, self._settings.trim_threshold_dbfs, 0.0) is None:
            raise RecorderSilentError("no sound above the threshold")
        start, end = 0, total
        if self._settings.trim:
            span = trim_silence(
                envelope, columns_per_s, self._settings.trim_threshold_dbfs, self._settings.trim_margin_s
            )
            assert span is not None
            start = min(total, round(span[0] * rate))
            end = max(start, min(total, round(span[1] * rate)))
        gain = 1.0
        if self._settings.normalize:
            # Every column that touches the kept part: the peak is never underestimated.
            kept = envelope[start // column : -(-end // column)]
            gain = normalize_gain(float(kept.max()), self._settings.normalize_peak_dbfs)
        path = wav.path
        if (start, end) != (0, total) or gain != 1.0:
            path = self._rewrite(wav, start, end, gain)
        gain_db = 20.0 * math.log10(gain)
        _log.info(
            "Recording saved (%s): %.2f s, trimmed %.2f s + %.2f s, gain %+.1f dB",
            reason.value,
            (end - start) / rate,
            start / rate,
            (total - end) / rate,
            gain_db,
        )
        return RecordingResult(
            wav_path=path,
            duration_s=(end - start) / rate,
            trimmed_start_s=start / rate,
            trimmed_end_s=(total - end) / rate,
            stop_reason=reason,
            gain_db=gain_db,
        )

    def _rewrite(self, wav: TempWav, start: int, end: int, gain: float) -> Path:
        """A new temporary WAV with frames start…end times `gain`; the old one is deleted."""
        try:
            target = TempWav(self._temp_dir, wav.sample_rate, wav.channels)
        except OSError as error:
            raise _write_error(error) from error
        factor = np.float32(gain)
        try:
            for first in range(start, end, _COPY_FRAMES):
                block = read_frames(wav.path, first, min(_COPY_FRAMES, end - first))
                target.write(block * factor if gain != 1.0 else block)
            target.close()
        except OSError as error:
            target.delete()
            raise _write_error(error) from error
        except BaseException:
            target.delete()
            raise
        wav.delete()
        with self._lock:
            self._wav = target
        return target.path


def _as_recorder_error(error: BaseException) -> RecorderError:
    if isinstance(error, RecorderError):
        return error
    if isinstance(error, OSError):
        return _write_error(error)
    return RecorderDeviceError(f"{type(error).__name__}: {error}")


def _write_error(error: OSError) -> RecorderError:
    if error.errno in _DISK_FULL_ERRNOS:
        return RecorderDiskFullError(detail=str(error))
    return RecorderDeviceError(f"{type(error).__name__}: {error}")


def _frame_peaks(block: AudioFrames) -> AudioFrames:
    """The highest |sample| of each frame, across channels."""
    return np.abs(block).max(axis=1)


def _any_at_or_above(block: AudioFrames, dbfs: float) -> bool:
    return bool(np.abs(block).max() >= dbfs_to_amplitude(dbfs))


def _fit_channels(block: AudioFrames, channels: int) -> AudioFrames:
    """The block as float32 (frames, channels): the backend should already deliver that."""
    data = np.asarray(block, dtype=np.float32)
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    if data.shape[1] == channels:
        return data
    if channels == 1:
        return data.mean(axis=1, keepdims=True, dtype=np.float32)
    if data.shape[1] == 1:
        return np.repeat(data, channels, axis=1)
    return np.ascontiguousarray(data[:, :channels])
