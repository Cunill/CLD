"""M8 · FFmpeg bridge: the only module that runs ffmpeg/ffprobe (block B7).

- Processes start without a shell and without a console window; stderr is always drained in
  parallel, so no pipe can fill up and block (`_process`).
- Paths go to ffmpeg absolute and as `file:` URLs: accents, spaces, ':' and long Windows paths work.
- Every failure becomes an FfmpegError whose message_key is one of the ERROR_* constants.
"""

from __future__ import annotations

from passimaker.ffmpeg._audio import decode_audio, measure_loudness, probe, waveform
from passimaker.ffmpeg._locate import locate
from passimaker.ffmpeg._video import FfmpegVideoWriter, extract_frames, open_encoder
from passimaker.ffmpeg.types import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    DEFAULT_ENCODER_SETTINGS,
    ENV_VAR,
    ERROR_ABORTED,
    ERROR_DISK_FULL,
    ERROR_ENCODE,
    ERROR_FAILED,
    ERROR_FILE_NOT_FOUND,
    ERROR_NO_AUDIO,
    ERROR_NOT_FOUND,
    ERROR_TIMEOUT,
    ERROR_UNREADABLE,
    ERROR_WRITE,
    EncoderSettings,
    FfmpegError,
    FfmpegPaths,
    Loudness,
    MediaInfo,
    PcmFile,
    VideoWriter,
)

__all__ = [
    "AUDIO_CHANNELS",
    "AUDIO_SAMPLE_RATE",
    "DEFAULT_ENCODER_SETTINGS",
    "ENV_VAR",
    "ERROR_ABORTED",
    "ERROR_DISK_FULL",
    "ERROR_ENCODE",
    "ERROR_FAILED",
    "ERROR_FILE_NOT_FOUND",
    "ERROR_NOT_FOUND",
    "ERROR_NO_AUDIO",
    "ERROR_TIMEOUT",
    "ERROR_UNREADABLE",
    "ERROR_WRITE",
    "EncoderSettings",
    "FfmpegError",
    "FfmpegPaths",
    "FfmpegVideoWriter",
    "Loudness",
    "MediaInfo",
    "PcmFile",
    "VideoWriter",
    "decode_audio",
    "extract_frames",
    "locate",
    "measure_loudness",
    "open_encoder",
    "probe",
    "waveform",
]
