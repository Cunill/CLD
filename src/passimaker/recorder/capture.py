"""Recorder (records to a temporary WAV) and Monitor (waves and level only), block C09.

Both capture in their own thread; every property and peaks_since() can be read from another
thread (the interface reads them RECORD_WAVE_REFRESH_HZ times per second).
"""

from __future__ import annotations

from pathlib import Path

from passimaker.recorder.backend import CaptureBackend
from passimaker.recorder.types import (
    AudioSource,
    PeakColumns,
    RecorderError,
    RecorderState,
    RecordingResult,
    RecordingSettings,
)

_NOT_IMPLEMENTED = "passimaker.recorder: implemented in block C09"


class Monitor:
    """Shows whether sound arrives from `source`, before recording: never writes to disk."""

    def __init__(self, source: AudioSource, *, backend: CaptureBackend | None = None) -> None:
        self._source = source
        self._backend = backend

    @property
    def source(self) -> AudioSource:
        return self._source

    def start(self) -> None:
        """Open the source; RecorderNoDeviceError or RecorderDeviceError if it cannot."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def stop(self) -> None:
        """Close the source; does nothing if not started or already stopped."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def level_dbfs(self) -> tuple[float, ...]:
        """Current peak level of each recorded channel, in dBFS (-inf for digital silence)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def peaks_since(self, index: int) -> tuple[PeakColumns, int]:
        """The columns after `index` (0 the first time) and the new index to pass next time.

        Only the last RECORD_WAVE_WINDOW_S are kept: if `index` is older, the columns start there.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def error(self) -> RecorderError | None:
        """The error that stopped the capture thread (e.g. the device was disconnected)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)


class Recorder:
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
        self._source = source
        self._temp_dir = temp_dir
        self._settings = settings or RecordingSettings()
        self._backend = backend

    @property
    def source(self) -> AudioSource:
        return self._source

    @property
    def settings(self) -> RecordingSettings:
        return self._settings

    def start(self) -> None:
        """Begin (WAITING with "Comença quan soni", otherwise RECORDING).

        RecorderDiskFullError(ERROR_NO_SPACE) with less than settings.min_free_bytes free;
        RecorderNoDeviceError or RecorderDeviceError if the source cannot be opened.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def stop(self) -> RecordingResult:
        """End and keep the recording: trims the silence (if settings.trim) and returns the WAV.

        Raises the interruption error (Recorder.error) if it was INTERRUPTED, and
        RecorderSilentError, deleting the WAV, if no sound was recorded.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def discard(self) -> None:
        """End and delete everything ([Descarta], closing the window or the program)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def state(self) -> RecorderState:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def error(self) -> RecorderError | None:
        """Why it was INTERRUPTED (the WAV is already deleted); None otherwise."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def elapsed_s(self) -> float:
        """Seconds saved so far (0 while WAITING)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def level_dbfs(self) -> tuple[float, ...]:
        """Current peak level of each recorded channel, in dBFS (-inf for digital silence)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def peaks_since(self, index: int) -> tuple[PeakColumns, int]:
        """The columns after `index` (0 the first time) and the new index; also while WAITING."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def overview(self, width: int) -> PeakColumns:
        """The waves of the whole recording reduced to `width` columns (after stopping, §1.7 ter)."""
        raise NotImplementedError(_NOT_IMPLEMENTED)
