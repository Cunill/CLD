"""Searching YouTube and reading the data of one video (contract §15)."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlsplit

from passimaker.common import CancelToken
from passimaker.model import defaults
from passimaker.youtube.backend import Info, YoutubeBackend, YtDlpBackend
from passimaker.youtube.consent import ConsentToken, require
from passimaker.youtube.errors import call, check_cancel
from passimaker.youtube.links import VIDEO_ID, watch_url
from passimaker.youtube.types import SearchResult, YoutubeBrokenError, YoutubeUnavailableError

THUMBNAIL_URL = "https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
"""320×180, the size the results list shows."""
THUMBNAIL_HOSTS = ("ytimg.com", "ggpht.com", "googleusercontent.com")
"""fetch_thumbnail only goes to YouTube's image servers."""
THUMBNAIL_MAX_BYTES = 2_000_000
MAX_SEARCH_RESULTS = 100
"""offset + limit: beyond this, "Més resultats" gives nothing more."""
_LIVE_STATUSES = {"is_live", "is_upcoming"}

_default_backend = YtDlpBackend()


def default_backend() -> YoutubeBackend:
    return _default_backend


def search(
    token: ConsentToken | None,
    query: str,
    limit: int = defaults.YOUTUBE_RESULTS_PER_PAGE,
    offset: int = 0,
    cancel: CancelToken | None = None,
    *,
    backend: YoutubeBackend | None = None,
) -> tuple[SearchResult, ...]:
    """Up to `limit` results for `query`, skipping the first `offset` ("Més resultats").

    Only videos (no channels or playlists). Blank query or nothing beyond MAX_SEARCH_RESULTS: ().
    Raises CancelledError if `cancel` was set meanwhile.
    """
    require(token)
    if limit < 1 or offset < 0:
        raise ValueError(f"limit {limit} and offset {offset}")
    text = " ".join(query.split())
    wanted = min(offset + limit, MAX_SEARCH_RESULTS)
    if not text or offset >= wanted:
        return ()
    check_cancel(cancel)
    found = call(lambda: (backend or _default_backend).extract_info(f"ytsearch{wanted}:{text}", flat=True))
    check_cancel(cancel)
    results: list[SearchResult] = []
    for entry in cast(list[Any], found.get("entries") or []):
        if isinstance(entry, dict) and _is_video(cast(Info, entry)):
            results.append(_result(cast(Info, entry)))
    return tuple(results[offset:wanted])


def resolve(
    token: ConsentToken | None,
    video_id: str,
    cancel: CancelToken | None = None,
    *,
    backend: YoutubeBackend | None = None,
) -> SearchResult:
    """The data of one video, for a pasted link (see links.parse_link).

    Live streams and long videos are returned (the interface greys them out); a private, deleted or
    restricted video raises YoutubeUnavailableError.
    """
    require(token)
    _check_id(video_id)
    check_cancel(cancel)
    info = call(lambda: (backend or _default_backend).extract_info(watch_url(video_id), flat=False))
    check_cancel(cancel)
    if info.get("id") != video_id:
        raise YoutubeBrokenError(f"asked for {video_id}, yt-dlp answered {info.get('id')!r}")
    return _result(info)


def fetch_thumbnail(
    token: ConsentToken | None,
    url: str,
    cancel: CancelToken | None = None,
    *,
    backend: YoutubeBackend | None = None,
) -> bytes:
    """The bytes of a result's thumbnail (320 px, kept only in memory; the interface decodes them).

    Only https URLs of YouTube's image servers (THUMBNAIL_HOSTS); anything else is a ValueError.
    """
    require(token)
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in THUMBNAIL_HOSTS):
        raise ValueError(f"not a YouTube thumbnail: {url}")
    check_cancel(cancel)
    data = call(lambda: (backend or _default_backend).fetch(url, THUMBNAIL_MAX_BYTES))
    check_cancel(cancel)
    return data


def is_live(info: Info) -> bool:
    return info.get("is_live") is True or info.get("live_status") in _LIVE_STATUSES


def _check_id(video_id: str) -> None:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError(f"not a video id: {video_id!r}")


def _is_video(entry: Info) -> bool:
    """Search entries can also be channels or playlists (ie_key YoutubeTab)."""
    video_id = entry.get("id")
    ie_key = entry.get("ie_key")
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        return False
    return ie_key in (None, "Youtube")


def _result(info: Info) -> SearchResult:
    video_id = str(info.get("id"))
    if not VIDEO_ID.fullmatch(video_id):
        raise YoutubeUnavailableError(detail=f"not a video: {video_id!r}")
    duration = info.get("duration")
    channel = info.get("channel") or info.get("uploader") or ""
    return SearchResult(
        video_id=video_id,
        title=str(info.get("title") or video_id),
        channel=str(channel),
        duration_s=float(duration) if isinstance(duration, int | float) and duration > 0 else None,
        thumbnail_url=THUMBNAIL_URL.format(video_id=video_id),
        is_live=is_live(info),
        url=watch_url(video_id),
    )
