"""Recognising YouTube video links (pure, no network)."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_PATH_PREFIXES = ("shorts", "embed", "live", "v")


def parse_link(text: str) -> str | None:
    """The video id of a YouTube video link, or None if `text` is not one.

    Accepts youtube.com/watch?v=…, youtu.be/…, music.youtube.com/watch?v=…, /shorts/…, /embed/… and
    /live/…, with or without the scheme and with extra parameters (&t=30s, &list=…).
    """
    candidate = text.strip()
    if not candidate or any(c.isspace() for c in candidate):
        return None
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    found: str | None = None
    if host in _SHORT_HOSTS:
        found = segments[0] if len(segments) == 1 else None
    elif host in _HOSTS:
        if segments == ["watch"]:
            values = parse_qs(parts.query).get("v", [])
            found = values[0] if len(values) == 1 else None
        elif len(segments) == 2 and segments[0] in _PATH_PREFIXES:
            found = segments[1]
    return found if found is not None and VIDEO_ID.fullmatch(found) else None


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
