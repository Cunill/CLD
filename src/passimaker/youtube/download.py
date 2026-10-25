"""Downloading the original audio of a video (block C03; the MP3 conversion is ffmpeg.convert_to_mp3)."""

from __future__ import annotations

from pathlib import Path

from passimaker.common import CancelToken, ProgressCallback
from passimaker.youtube.consent import ConsentToken, require


def download_audio(
    token: ConsentToken | None,
    video_id: str,
    temp_dir: Path,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> Path:
    """Downloads the best audio stream as is (M4A/WebM, no post-processing) into `temp_dir`; returns its path.

    Raises YoutubeTooLongError beyond defaults.YOUTUBE_MAX_DURATION_S and YoutubeUnavailableError
    (ERROR_LIVE) for live streams. Cancelling leaves no file behind.
    """
    require(token)
    raise NotImplementedError("passimaker.youtube: implemented in block C03")
