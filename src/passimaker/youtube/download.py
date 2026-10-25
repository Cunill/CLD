"""Downloading the original audio of a video (contract §15; the MP3 conversion is ffmpeg.convert_to_mp3)."""

from __future__ import annotations

import shutil
import tempfile
from concurrent.futures import CancelledError
from pathlib import Path

from passimaker.common import CancelToken, ProgressCallback
from passimaker.model import defaults
from passimaker.youtube.backend import Info, YoutubeBackend
from passimaker.youtube.consent import ConsentToken, require
from passimaker.youtube.errors import call, check_cancel
from passimaker.youtube.links import VIDEO_ID, watch_url
from passimaker.youtube.search import default_backend, is_live
from passimaker.youtube.types import (
    ERROR_LIVE,
    YoutubeBrokenError,
    YoutubeTooLongError,
    YoutubeUnavailableError,
)

FOLDER_PREFIX = "youtube_"
"""Each download goes to its own new folder inside temp_dir, removed if the download does not finish."""


def download_audio(
    token: ConsentToken | None,
    video_id: str,
    temp_dir: Path,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
    *,
    backend: YoutubeBackend | None = None,
) -> Path:
    """Downloads the best audio stream as is (M4A/WebM, no post-processing) into `temp_dir`; returns its path.

    The file is inside a new folder of `temp_dir` (FOLDER_PREFIX…), which the caller removes with
    temp_dir once converted. Raises YoutubeTooLongError beyond defaults.YOUTUBE_MAX_DURATION_S and
    YoutubeUnavailableError (ERROR_LIVE) for live streams, both before downloading anything.
    progress(done, total) in bytes, never going back and ending at (total, total).
    Cancelling raises CancelledError within a fraction of a second of data and leaves no file behind.
    """
    require(token)
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError(f"not a video id: {video_id!r}")
    source = backend or default_backend()
    check_cancel(cancel)
    info = call(lambda: source.extract_info(watch_url(video_id), flat=False))
    _check_downloadable(info, video_id)
    check_cancel(cancel)
    folder = Path(tempfile.mkdtemp(prefix=FOLDER_PREFIX, dir=temp_dir))
    tracker = _Progress(progress, cancel)
    try:
        path = call(lambda: source.download(info, folder, tracker.hook))
        check_cancel(cancel)
        if not path.is_file() or path.parent.resolve() != folder.resolve():
            raise YoutubeBrokenError(f"downloaded file not found in {folder}: {path}")
    except BaseException as error:
        shutil.rmtree(folder, ignore_errors=True)
        if cancel is not None and cancel.cancelled and not isinstance(error, CancelledError):
            raise CancelledError from error
        raise
    tracker.finished(path.stat().st_size)
    return path


def _check_downloadable(info: Info, video_id: str) -> None:
    if info.get("id") != video_id:
        raise YoutubeBrokenError(f"asked for {video_id}, yt-dlp answered {info.get('id')!r}")
    if is_live(info):
        raise YoutubeUnavailableError(ERROR_LIVE, f"{video_id}: live_status {info.get('live_status')!r}")
    duration = info.get("duration")
    if isinstance(duration, int | float) and duration > defaults.YOUTUBE_MAX_DURATION_S:
        raise YoutubeTooLongError(f"{video_id}: {duration} s")


class _Progress:
    """Turns yt-dlp's progress hook into ProgressCallback, and stops the download when cancelled."""

    def __init__(self, progress: ProgressCallback | None, cancel: CancelToken | None) -> None:
        self._progress = progress
        self._cancel = cancel
        self._done = 0
        self._total = 0

    def hook(self, status: Info) -> None:
        # yt-dlp calls the hooks for every received block: raising here stops the download.
        check_cancel(self._cancel)
        done = status.get("downloaded_bytes")
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if isinstance(total, int | float) and total > 0:
            self._total = max(self._total, int(total))
        if isinstance(done, int | float):
            self._done = max(self._done, int(done))
        self._report()

    def finished(self, size: int) -> None:
        self._done = self._total = max(self._done, self._total, size)
        self._report()

    def _report(self) -> None:
        if self._progress is not None and self._total > 0:
            self._progress(min(self._done, self._total), self._total)
