"""M16 · Recording the sound of the computer, "Grava el que sona" (decision 0013; blocks C07-C10).

- Captures what a sound output plays (WASAPI loopback), or a microphone or line input only when
  the user picks it (G6). No network (the architecture test checks it), no notice (G2), no Qt.
- Writes a temporary WAV while recording; saved only by stop() or the automatic stop for silence.
  Any interruption, also the maximum duration, deletes it and raises a RecorderError (G1, G5).
- The sound system is behind CaptureBackend (technology chosen in block C08); tests use a fake.
- Every failure is a RecorderError whose message_key is one of the ERROR_* constants.

- Saving trims the silence at both ends and raises a quiet recording to a peak of
  defaults.RECORD_NORMALIZE_PEAK_DBFS (never higher; user's decision of 26/10/2026).

Contract: docs/CONTRACTES.md §16 (block C07); implemented in block C09 with soundcard (G10).
"""

from __future__ import annotations

from passimaker.recorder.backend import CaptureBackend, CaptureStream, SoundcardBackend
from passimaker.recorder.capture import Monitor, Recorder
from passimaker.recorder.devices import list_sources
from passimaker.recorder.silence import trim_silence
from passimaker.recorder.types import (
    ERROR_DEVICE,
    ERROR_DEVICE_LOST,
    ERROR_DISK_FULL,
    ERROR_MAX_DURATION,
    ERROR_MICROPHONE_DENIED,
    ERROR_NO_DEVICE,
    ERROR_NO_SPACE,
    ERROR_SILENT,
    AudioFrames,
    AudioSource,
    PeakColumns,
    RecorderDeviceError,
    RecorderDeviceLostError,
    RecorderDiskFullError,
    RecorderError,
    RecorderMaxDurationError,
    RecorderMicrophoneDeniedError,
    RecorderNoDeviceError,
    RecorderSilentError,
    RecorderState,
    RecordingResult,
    RecordingSettings,
    SourceKind,
    StopReason,
)
from passimaker.recorder.wavwriter import TEMP_PREFIX, remove_leftovers

__all__ = [
    "ERROR_DEVICE",
    "ERROR_DEVICE_LOST",
    "ERROR_DISK_FULL",
    "ERROR_MAX_DURATION",
    "ERROR_MICROPHONE_DENIED",
    "ERROR_NO_DEVICE",
    "ERROR_NO_SPACE",
    "ERROR_SILENT",
    "TEMP_PREFIX",
    "AudioFrames",
    "AudioSource",
    "CaptureBackend",
    "CaptureStream",
    "Monitor",
    "PeakColumns",
    "Recorder",
    "RecorderDeviceError",
    "RecorderDeviceLostError",
    "RecorderDiskFullError",
    "RecorderError",
    "RecorderMaxDurationError",
    "RecorderMicrophoneDeniedError",
    "RecorderNoDeviceError",
    "RecorderSilentError",
    "RecorderState",
    "RecordingResult",
    "RecordingSettings",
    "SoundcardBackend",
    "SourceKind",
    "StopReason",
    "list_sources",
    "remove_leftovers",
    "trim_silence",
]
