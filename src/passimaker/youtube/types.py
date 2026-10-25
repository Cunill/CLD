"""Public types, errors and message keys of the YouTube music module (contract §15)."""

from __future__ import annotations

from dataclasses import dataclass

from passimaker.common import PassiMakerError

# Message keys (passimaker.i18n) of the errors raised by this module (ESPECIFICACIO §1.7 bis, "Errors").
ERROR_OFFLINE = "youtube.offline"
"""No internet connection."""
ERROR_INVALID_LINK = "youtube.invalid_link"
"""The pasted text is a link, but not to a YouTube video (shown by the interface when parse_link fails)."""
ERROR_UNAVAILABLE = "youtube.unavailable"
"""Private, deleted, age-restricted or country-restricted video."""
ERROR_LIVE = "youtube.live"
"""A live stream in progress."""
ERROR_BROKEN = "youtube.broken"
"""YouTube changed and yt-dlp no longer works (detail: yt-dlp's message, for the log)."""
ERROR_TOO_LONG = "youtube.too_long"
"""Longer than defaults.YOUTUBE_MAX_DURATION_S."""
ERROR_CONSENT = "youtube.consent"
"""Called without a valid ConsentToken: nothing was done, not even a connection attempt."""


class YoutubeError(PassiMakerError):
    """Base of the errors of this module; message_key is one of the ERROR_* constants."""


class YoutubeOfflineError(YoutubeError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_OFFLINE, detail)


class YoutubeUnavailableError(YoutubeError):
    """The video cannot be downloaded: ERROR_UNAVAILABLE, or ERROR_LIVE for a live stream."""

    def __init__(self, message_key: str = ERROR_UNAVAILABLE, detail: str = "") -> None:
        super().__init__(message_key, detail)


class YoutubeBrokenError(YoutubeError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_BROKEN, detail)


class YoutubeTooLongError(YoutubeError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_TOO_LONG, detail)


class YoutubeConsentError(YoutubeError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ERROR_CONSENT, detail)


@dataclass(frozen=True, slots=True)
class SearchResult:
    video_id: str
    title: str
    channel: str
    duration_s: float | None
    """None when YouTube does not give it (live streams, some flat search results)."""
    thumbnail_url: str
    is_live: bool
    url: str
    """Canonical watch URL (https://www.youtube.com/watch?v=<video_id>), for [Obre a YouTube]."""
