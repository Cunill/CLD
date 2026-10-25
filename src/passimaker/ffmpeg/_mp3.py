"""MP3 conversion for the songs downloaded from YouTube (contract §8; implemented in block C04)."""

from __future__ import annotations

from pathlib import Path

from passimaker.common import CancelToken, ProgressCallback
from passimaker.ffmpeg.types import Mp3Tags


def convert_to_mp3(
    source: Path,
    dest: Path,
    bitrate_kbps: int,
    tags: Mp3Tags,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> None:
    """Converts any audio file to MP3 (libmp3lame, constant `bitrate_kbps`, 48 kHz stereo, ID3 `tags`).

    Writes to a temporary file next to `dest` and renames it at the end: if it fails or is cancelled,
    `dest` is not created. Errors: FfmpegError with the ERROR_* keys of this module.
    """
    raise NotImplementedError("passimaker.ffmpeg.convert_to_mp3: implemented in block C04")
