"""M8 · FFmpeg bridge: the only module that runs ffmpeg/ffprobe (block B7)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from passi.common import PassiError, RGBImage

ENV_VAR = "PASSI_FFMPEG"
"""Directory containing ffmpeg and ffprobe; takes precedence over the bundled copy."""

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2


class FfmpegError(PassiError):
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
    true_peak_dbfs: float


@dataclass(frozen=True, slots=True)
class EncoderSettings:
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    profile: str = "high"
    audio_bitrate: str = "192k"


DEFAULT_ENCODER_SETTINGS = EncoderSettings()


class VideoWriter(Protocol):
    def write(self, frame: RGBImage) -> None: ...

    def close(self) -> None:
        """Finishes encoding; raises FfmpegError if ffmpeg failed."""
        ...

    def abort(self) -> None:
        """Stops ffmpeg and deletes the partial output (< 2 s)."""
        ...


def locate() -> FfmpegPaths:
    raise NotImplementedError("B7")


def probe(path: Path) -> MediaInfo:
    raise NotImplementedError("B7")


def decode_audio(path: Path, dest: Path, start_s: float = 0.0, end_s: float | None = None) -> PcmFile:
    raise NotImplementedError("B7")


def measure_loudness(path: Path) -> Loudness:
    raise NotImplementedError("B7")


def open_encoder(
    dest: Path,
    width: int,
    height: int,
    audio_wav: Path | None,
    settings: EncoderSettings = DEFAULT_ENCODER_SETTINGS,
) -> VideoWriter:
    raise NotImplementedError("B7")


def extract_frames(video: Path, times_s: Sequence[float]) -> list[RGBImage]:
    raise NotImplementedError("B7")


def waveform(path: Path, points: int) -> NDArray[np.float32]:
    """Peak amplitude (0-1) per bucket, `points` buckets over the whole file."""
    raise NotImplementedError("B7")
