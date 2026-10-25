"""The part that talks to YouTube, behind a small protocol so tests can replace it (contract §15).

YtDlpBackend is the real one: yt-dlp as a library, imported only when a method runs (never at
import time, decision 0012). It downloads the original audio stream as is: no FFmpeg from yt-dlp,
the conversion is passimaker.ffmpeg.convert_to_mp3. Deno (decision 0012, block C02) solves
YouTube's JavaScript challenges; yt-dlp launches it with a hidden window.

The tests use tests/fakes/youtube.py (FakeYoutubeBackend).
"""

from __future__ import annotations

import logging
import sys
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, cast

_log = logging.getLogger(__name__)

SOCKET_TIMEOUT_S = 30.0
"""Seconds without an answer before a request fails (yt-dlp and the thumbnails)."""
DENO_EXE = "deno.exe" if sys.platform == "win32" else "deno"
AUDIO_FORMAT = "bestaudio[audio_channels<=?2]/bestaudio"
"""Stereo first: with Deno, plain "bestaudio" chose a 5.1 AAC three times the size of the stereo Opus
(docs/sessions/C02.md). "<=?" also takes formats that do not say their channels; without any stereo
format, the best audio."""
INFO_FORMAT = AUDIO_FORMAT + "/best"
"""Only for reading a video's data (extract_info): yt-dlp also selects formats then, and a live stream
has no audio-only format; "/best" lets it through so download_audio can say it is a live stream
(ERROR_LIVE) instead of "Requested format is not available". Downloading always uses AUDIO_FORMAT."""

type Info = Mapping[str, Any]
"""yt-dlp's information dictionary (one video, or a search with its "entries")."""
type DownloadHook = Callable[[Info], None]
"""yt-dlp's progress hook: called with {"status", "downloaded_bytes", "total_bytes"…}; may raise to stop."""


class YoutubeBackend(Protocol):
    """What passimaker.youtube needs from YouTube. Every method may block for seconds and raise
    whatever yt-dlp or the network raise; errors.translate turns that into YoutubeError."""

    def extract_info(self, url: str, *, flat: bool) -> Info:
        """The information of a video or of a search ("ytsearchN:query"), without downloading.

        flat=True lists the entries of a search without opening each video (fast, fewer fields).
        """
        ...

    def download(self, info: Info, folder: Path, hook: DownloadHook) -> Path:
        """Downloads the best audio stream of `info` (from extract_info) into `folder`; returns the file."""
        ...

    def fetch(self, url: str, max_bytes: int) -> bytes:
        """The bytes at `url` (a thumbnail); raises ValueError beyond `max_bytes`."""
        ...


class YtDlpBackend:
    """The real backend: yt-dlp, the system's proxy settings and the Deno of the package."""

    def extract_info(self, url: str, *, flat: bool) -> Info:
        options = self._options()
        options["format"] = INFO_FORMAT
        if flat:
            options["extract_flat"] = "in_playlist"
        with self._ydl(options) as ydl:
            return cast(Info, ydl.sanitize_info(ydl.extract_info(url, download=False)))

    def download(self, info: Info, folder: Path, hook: DownloadHook) -> Path:
        options = self._options()
        options["outtmpl"] = str(folder / "%(id)s.%(ext)s")
        options["progress_hooks"] = [hook]
        with self._ydl(options) as ydl:
            result = cast(Info, ydl.process_ie_result(dict(info), download=True))
        downloads = cast(list[Info], result.get("requested_downloads") or [])
        if not downloads or not downloads[0].get("filepath"):
            raise RuntimeError("yt-dlp did not report the downloaded file")
        return Path(str(downloads[0]["filepath"]))

    def fetch(self, url: str, max_bytes: int) -> bytes:
        # urllib uses the system's proxy settings, as yt-dlp does.
        with urllib.request.urlopen(url, timeout=SOCKET_TIMEOUT_S) as response:
            data = cast(bytes, response.read(max_bytes + 1))
        if len(data) > max_bytes:
            raise ValueError(f"more than {max_bytes} bytes at {url}")
        return data

    @staticmethod
    def _options() -> dict[str, Any]:
        options: dict[str, Any] = {
            "logger": _YtDlpLogger(),
            "quiet": True,
            "noprogress": True,
            "color": {"stdout": "no_color", "stderr": "no_color"},
            "socket_timeout": SOCKET_TIMEOUT_S,
            "retries": 3,
            "extractor_retries": 2,
            "cachedir": False,  # nothing written outside the folders we choose
            "noplaylist": True,
            "format": AUDIO_FORMAT,
            "fixup": "never",  # no FFmpeg from yt-dlp (rule 7: passimaker.ffmpeg converts)
            "postprocessors": [],
            "overwrites": True,
            "continuedl": False,
        }
        deno = find_deno()
        if deno is not None:
            options["js_runtimes"] = {"deno": {"path": str(deno)}}
        return options

    @staticmethod
    def _ydl(options: dict[str, Any]) -> Any:
        import yt_dlp

        return yt_dlp.YoutubeDL(cast(Any, options))


def find_deno() -> Path | None:
    """deno.exe of the package (bin/, next to ffmpeg.exe) or of the `deno` Python package.

    None: yt-dlp looks for Deno on the PATH and, without it, falls back to the clients that need
    no JavaScript (deprecated, some formats may be missing; docs/sessions/C02.md).
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle, str):
        candidate = Path(bundle) / DENO_EXE
        return candidate if candidate.is_file() else None
    try:
        from deno import find_deno_bin  # pyright: ignore[reportMissingTypeStubs]
    except ImportError:
        return None
    try:
        return Path(find_deno_bin())
    except FileNotFoundError:
        return None


class _YtDlpLogger:
    """yt-dlp's messages go to the program's log (decision 0012: the detail of a failure is there)."""

    def debug(self, msg: str) -> None:
        # yt-dlp sends its "info" messages through debug, prefixed with "[debug] " only when verbose.
        _log.debug("%s", msg)

    def info(self, msg: str) -> None:
        _log.info("%s", msg)

    def warning(self, msg: str) -> None:
        _log.warning("%s", msg)

    def error(self, msg: str) -> None:
        _log.error("%s", msg)
