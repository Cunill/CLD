"""M15 · Music from YouTube (decision 0012; blocks C01-C06).

- The only module of the program that may open network connections; the rest stays offline.
- No connection before the user accepts the notice: every function that can connect takes a
  ConsentToken (consent.grant) and raises YoutubeConsentError without one, before doing anything.
- yt-dlp is imported only inside the functions that use it, never at import time.
- No Qt (rule 1). Every failure is a YoutubeError whose message_key is one of the ERROR_* constants.

- The functions that reach YouTube take an optional `backend` (YoutubeBackend); the real one is
  YtDlpBackend, the tests use tests/fakes/youtube.py. Cancelling raises CancelledError.

Contract: docs/CONTRACTES.md §15 (block C01); implemented in block C03.
"""

from __future__ import annotations

from passimaker.youtube import consent
from passimaker.youtube.backend import YoutubeBackend, YtDlpBackend
from passimaker.youtube.consent import ConsentToken
from passimaker.youtube.download import download_audio
from passimaker.youtube.files import safe_target_path
from passimaker.youtube.links import parse_link, watch_url
from passimaker.youtube.search import fetch_thumbnail, resolve, search
from passimaker.youtube.types import (
    ERROR_BLOCKED,
    ERROR_BROKEN,
    ERROR_CONSENT,
    ERROR_INVALID_LINK,
    ERROR_LIVE,
    ERROR_OFFLINE,
    ERROR_TOO_LONG,
    ERROR_UNAVAILABLE,
    SearchResult,
    YoutubeBlockedError,
    YoutubeBrokenError,
    YoutubeConsentError,
    YoutubeError,
    YoutubeOfflineError,
    YoutubeTooLongError,
    YoutubeUnavailableError,
)

__all__ = [
    "ERROR_BLOCKED",
    "ERROR_BROKEN",
    "ERROR_CONSENT",
    "ERROR_INVALID_LINK",
    "ERROR_LIVE",
    "ERROR_OFFLINE",
    "ERROR_TOO_LONG",
    "ERROR_UNAVAILABLE",
    "ConsentToken",
    "SearchResult",
    "YoutubeBackend",
    "YoutubeBlockedError",
    "YoutubeBrokenError",
    "YoutubeConsentError",
    "YoutubeError",
    "YoutubeOfflineError",
    "YoutubeTooLongError",
    "YoutubeUnavailableError",
    "YtDlpBackend",
    "consent",
    "download_audio",
    "fetch_thumbnail",
    "parse_link",
    "resolve",
    "safe_target_path",
    "search",
    "watch_url",
]
