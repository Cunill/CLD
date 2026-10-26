"""Public types, errors and message keys of the recorder (contract §16, ESPECIFICACIO §1.7 ter)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from passimaker.common import PassiMakerError
from passimaker.model import defaults

type AudioFrames = NDArray[np.float32]
"""Captured samples, shape (frames, channels), float32 in [-1, 1], at the source's own sample rate."""

type PeakColumns = NDArray[np.float32]
"""Wave columns, shape (columns, channels, 2): minimum and maximum of each column, in [-1, 1]."""

# Message keys (passimaker.i18n) of the errors raised by this module (ESPECIFICACIO §1.7 ter, "Errors").
ERROR_NO_DEVICE = "recorder.no_device"
"""There is no sound output to record from (list_sources found none, or the chosen one is gone)."""
ERROR_DEVICE_LOST = "recorder.device_lost"
"""The output changed or was disconnected while recording (e.g. Bluetooth headphones)."""
ERROR_SILENT = "recorder.silent"
"""Stopped by the user, but nothing above the threshold was recorded."""
ERROR_DISK_FULL = "recorder.disk_full"
"""Free space fell below defaults.RECORD_MIN_FREE_BYTES while recording."""
ERROR_NO_SPACE = "recorder.no_space"
"""Less than defaults.RECORD_MIN_FREE_BYTES free before starting: nothing was recorded."""
ERROR_MAX_DURATION = "recorder.max_duration"
"""defaults.RECORD_MAX_DURATION_S reached (decision 0013, G5: it counts as interrupted)."""
ERROR_DEVICE = "recorder.device_error"
"""Any other failure of the sound system (detail: the backend's message, for the log)."""
ERROR_MICROPHONE_DENIED = "recorder.microphone_denied"
"""Windows denies the desktop programs the microphone (0x80070005, block C08): says where to allow it."""


class RecorderError(PassiMakerError):
    """Base of the errors of this module; message_key is one of the ERROR_* constants.

    Every error raised once a recording has begun means the temporary WAV is already deleted
    (decision 0013, G1): a recording is saved only by Recorder.stop().
    """


class RecorderNoDeviceError(RecorderError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_NO_DEVICE, detail)


class RecorderDeviceLostError(RecorderError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_DEVICE_LOST, detail)


class RecorderSilentError(RecorderError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_SILENT, detail)


class RecorderDiskFullError(RecorderError):
    """ERROR_DISK_FULL while recording, or ERROR_NO_SPACE when start() refuses to begin."""

    def __init__(self, message_key: str = ERROR_DISK_FULL, detail: str = "") -> None:
        super().__init__(message_key, detail)


class RecorderMaxDurationError(RecorderError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_MAX_DURATION, detail)


class RecorderDeviceError(RecorderError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_DEVICE, detail)


class RecorderMicrophoneDeniedError(RecorderError):
    """An input (microphone, line) cannot be opened because of Windows' privacy settings."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_MICROPHONE_DENIED, detail)


class SourceKind(StrEnum):
    OUTPUT_LOOPBACK = "output_loopback"
    """What a sound output plays (WASAPI loopback): the default and the usual choice."""
    INPUT = "input"
    """A microphone or line input: used only when the user picks it (decision 0013, G6)."""


@dataclass(frozen=True, slots=True)
class AudioSource:
    id: str
    """Opaque identifier given by the capture backend; stable while the device stays connected."""
    name: str
    """As Windows shows it ("Altaveus (Realtek)"); the interface adds "per defecte"."""
    kind: SourceKind
    is_default: bool
    """The default output of Windows (or the default input, for SourceKind.INPUT)."""
    sample_rate: int
    channels: int
    """Channels of the device (1, 2, 6…); the recording keeps at most two (a stereo mix)."""

    @property
    def recorded_channels(self) -> int:
        """Lanes of the waves and channels of the WAV: 1 for a mono source, otherwise 2."""
        return 1 if self.channels == 1 else 2


class StopReason(StrEnum):
    """Why a saved recording ended. Any other cause is an interruption: a RecorderError (G1)."""

    USER = "user"
    """[■ Atura]."""
    SILENCE = "silence"
    """The automatic stop after defaults.RECORD_SILENCE_STOP_S of silence."""


class RecorderState(StrEnum):
    IDLE = "idle"
    """Created, start() not called yet."""
    WAITING = "waiting"
    """Started with "Comença quan soni": capturing and showing the waves, nothing saved yet."""
    RECORDING = "recording"
    FINISHED = "finished"
    """Stopped on its own by the silence: stop() returns the result with StopReason.SILENCE."""
    INTERRUPTED = "interrupted"
    """Ended by an error; the file is already deleted and stop() raises Recorder.error."""
    CLOSED = "closed"
    """After stop() or discard()."""


@dataclass(frozen=True, slots=True)
class RecordingSettings:
    """The options of the window ("Comença quan soni", automatic stop) and the limits (defaults.py)."""

    start_when_sound: bool = defaults.RECORD_START_WHEN_SOUND
    start_threshold_dbfs: float = defaults.RECORD_START_THRESHOLD_DBFS
    silence_stop: bool = defaults.RECORD_SILENCE_STOP_ENABLED
    silence_stop_s: float = defaults.RECORD_SILENCE_STOP_S
    silence_threshold_dbfs: float = defaults.RECORD_SILENCE_THRESHOLD_DBFS
    trim: bool = defaults.RECORD_TRIM_ENABLED
    trim_threshold_dbfs: float = defaults.RECORD_TRIM_THRESHOLD_DBFS
    trim_margin_s: float = defaults.RECORD_TRIM_MARGIN_S
    max_duration_s: float = defaults.RECORD_MAX_DURATION_S
    min_free_bytes: int = defaults.RECORD_MIN_FREE_BYTES
    peak_columns_per_s: int = defaults.RECORD_PEAK_COLUMNS_PER_S
    normalize: bool = defaults.RECORD_NORMALIZE_ENABLED
    normalize_peak_dbfs: float = defaults.RECORD_NORMALIZE_PEAK_DBFS


@dataclass(frozen=True, slots=True)
class RecordingResult:
    wav_path: Path
    """The temporary WAV, already trimmed; the caller converts it to MP3 and deletes it."""
    duration_s: float
    """Of the trimmed WAV."""
    trimmed_start_s: float
    """Silence removed from the start (0 if nothing or trimming is off)."""
    trimmed_end_s: float
    """Silence removed from the end."""
    stop_reason: StopReason
    gain_db: float = 0.0
    """Raised by the normalisation (0 if it was already loud enough or it is off); never negative."""
