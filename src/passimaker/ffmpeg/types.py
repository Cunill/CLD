"""Public types and constants of the FFmpeg bridge (contract §8)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from passimaker.common import PassiMakerError, RGBImage

ENV_VAR = "PASSIMAKER_FFMPEG"
"""Directory containing ffmpeg and ffprobe; takes precedence over the bundled copy."""

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2

# Message keys (passimaker.i18n) of the errors raised by this module.
ERROR_NOT_FOUND = "ffmpeg.not_found"
"""ffmpeg or ffprobe could not be found (detail: the places searched)."""
ERROR_FILE_NOT_FOUND = "ffmpeg.file_not_found"
"""The input file does not exist."""
ERROR_UNREADABLE = "ffmpeg.unreadable"
"""The input file is corrupt or in a format FFmpeg cannot read."""
ERROR_NO_AUDIO = "ffmpeg.no_audio"
"""The input file has no audio stream."""
ERROR_DISK_FULL = "ffmpeg.disk_full"
"""The output disk filled up while writing."""
ERROR_WRITE = "ffmpeg.write_error"
"""The output file could not be written (permissions, missing folder...)."""
ERROR_ENCODE = "ffmpeg.encode_error"
"""The encoder stopped with an error."""
ERROR_ABORTED = "ffmpeg.aborted"
"""The encoder was used after abort()."""
ERROR_TIMEOUT = "ffmpeg.timeout"
"""FFmpeg did not answer in time (very slow disk or network drive)."""
ERROR_FAILED = "ffmpeg.failed"
"""Any other FFmpeg failure (detail: the end of FFmpeg's error output)."""


class FfmpegError(PassiMakerError):
    """FFmpeg failed or is missing; message_key identifies the user message."""


@dataclass(frozen=True, slots=True)
class FfmpegPaths:
    ffmpeg: Path
    ffprobe: Path


@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration_s: float
    has_audio: bool
    sample_rate: int | None
    channels: int | None
    has_video: bool
    """A real video stream; a cover image embedded in a song does not count."""
    width: int | None
    height: int | None


@dataclass(frozen=True, slots=True)
class PcmFile:
    """Raw interleaved little-endian float32 stereo at 48 kHz."""

    path: Path
    frames: int


@dataclass(frozen=True, slots=True)
class Loudness:
    integrated_lufs: float
    """EBU R128 integrated loudness (0.1 LU steps); -70 or lower for silence (absolute gate)."""
    true_peak_dbfs: float
    """True peak (oversampled, 0.1 dB steps); -inf for silence."""


@dataclass(frozen=True, slots=True)
class EncoderSettings:
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    profile: str = "high"
    audio_bitrate: str = "192k"


DEFAULT_ENCODER_SETTINGS = EncoderSettings()


class VideoWriter(Protocol):
    def write(self, frame: RGBImage) -> None:
        """Sends one frame (height × width × 3, uint8); raises FfmpegError if ffmpeg failed."""
        ...

    def close(self) -> None:
        """Finishes encoding; raises FfmpegError if ffmpeg failed (the partial output is deleted)."""
        ...

    def abort(self) -> None:
        """Stops ffmpeg and deletes the partial output (< 2 s)."""
        ...
