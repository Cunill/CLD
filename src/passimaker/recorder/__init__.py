"""M16 · Recording the sound of the computer, "Grava el que sona" (decision 0013; blocks C07-C10).

- Captures what a sound output plays (WASAPI loopback), or a microphone or line input only when
  the user picks it (G6). No network (the architecture test checks it), no notice (G2), no Qt.
- Writes a temporary WAV while recording; saved only by stop() or the automatic stop for silence.
  Any interruption, also the maximum duration, deletes it and raises a RecorderError (G1, G5).
- The sound system is behind CaptureBackend (technology chosen in block C08); tests use a fake.
- Every failure is a RecorderError whose message_key is one of the ERROR_* constants.

Block C07 fixes the contract (docs/CONTRACTES.md §16): trim_silence works; the rest raises
NotImplementedError until block C09.
"""

from __future__ import annotations

from passimaker.recorder.backend import CaptureBackend, CaptureStream
from passimaker.recorder.capture import Monitor, Recorder
from passimaker.recorder.devices import list_sources
from passimaker.recorder.silence import trim_silence
from passimaker.recorder.types import (
    ERROR_DEVICE,
    ERROR_DEVICE_LOST,
    ERROR_DISK_FULL,
    ERROR_MAX_DURATION,
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
    "RecorderNoDeviceError",
    "RecorderSilentError",
    "RecorderState",
    "RecordingResult",
    "RecordingSettings",
    "SourceKind",
    "StopReason",
    "list_sources",
    "remove_leftovers",
    "trim_silence",
]
