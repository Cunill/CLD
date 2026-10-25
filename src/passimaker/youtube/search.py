"""Searching YouTube and reading the data of one video (block C03 implements it with yt-dlp)."""

from __future__ import annotations

from passimaker.common import CancelToken
from passimaker.model import defaults
from passimaker.youtube.consent import ConsentToken, require
from passimaker.youtube.types import SearchResult

_NOT_IMPLEMENTED = "passimaker.youtube: implemented in block C03"


def search(
    token: ConsentToken | None,
    query: str,
    limit: int = defaults.YOUTUBE_RESULTS_PER_PAGE,
    offset: int = 0,
    cancel: CancelToken | None = None,
) -> tuple[SearchResult, ...]:
    """Up to `limit` results for `query`, skipping the first `offset` ("Més resultats")."""
    require(token)
    raise NotImplementedError(_NOT_IMPLEMENTED)


def resolve(token: ConsentToken | None, video_id: str, cancel: CancelToken | None = None) -> SearchResult:
    """The data of one video, for a pasted link (see links.parse_link)."""
    require(token)
    raise NotImplementedError(_NOT_IMPLEMENTED)


def fetch_thumbnail(token: ConsentToken | None, url: str, cancel: CancelToken | None = None) -> bytes:
    """The bytes of a result's thumbnail (320 px, kept only in memory; the interface decodes them)."""
    require(token)
    raise NotImplementedError(_NOT_IMPLEMENTED)
