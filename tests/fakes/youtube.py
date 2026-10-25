"""Replacement for YouTube and yt-dlp (contract §15): saved answers, no network.

FakeYoutubeBackend implements passimaker.youtube.YoutubeBackend. Videos, search entries and
thumbnails are plain dictionaries shaped like yt-dlp's; `errors` makes a URL raise.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from passimaker.youtube.links import watch_url


def video_info(
    video_id: str,
    title: str = "Nuvole bianche",
    channel: str = "Ludovico Einaudi",
    duration: float | None = 357.0,
    live_status: str = "not_live",
    ext: str = "m4a",
) -> dict[str, Any]:
    """A video as yt-dlp's extract_info(download=False) describes it (the fields we read)."""
    return {
        "id": video_id,
        "title": title,
        "channel": channel,
        "uploader": channel,
        "duration": duration,
        "live_status": live_status,
        "is_live": live_status == "is_live",
        "ext": ext,
        "webpage_url": watch_url(video_id),
    }


def search_entry(video_id: str, title: str = "Resultat", duration: float | None = 200.0) -> dict[str, Any]:
    """A flat search entry (extract_flat), as yt-dlp lists them."""
    return {
        "_type": "url",
        "ie_key": "Youtube",
        "id": video_id,
        "url": watch_url(video_id),
        "title": title,
        "channel": "Canal",
        "duration": duration,
        "live_status": None,
    }


def numbered_id(index: int) -> str:
    """A valid, distinct 11-character video id."""
    return f"vid{index:08d}"


@dataclass
class FakeYoutubeBackend:
    videos: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    search_entries: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    thumbnails: dict[str, bytes] = field(default_factory=dict[str, bytes])
    errors: dict[str, BaseException] = field(default_factory=dict[str, BaseException])
    """URL (watch URL, "ytsearch…" or thumbnail) or "download:<id>" → exception to raise."""
    audio_size: int = 64_000
    chunk_size: int = 8_000
    on_chunk: Callable[[int], None] | None = None
    """Called after each written chunk with its index (tests cancel from here)."""
    report_total: bool = True
    """False: only total_bytes_estimate, as for some YouTube formats."""
    calls: list[str] = field(default_factory=list[str])
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, info: dict[str, Any]) -> None:
        self.videos[str(info["id"])] = info

    def extract_info(self, url: str, *, flat: bool) -> Mapping[str, Any]:
        self._record(f"extract_info {url} flat={flat}")
        self._maybe_raise(url)
        if url.startswith("ytsearch"):
            count_text, _, _query = url.removeprefix("ytsearch").partition(":")
            return {"_type": "playlist", "entries": self.search_entries[: int(count_text)]}
        video_id = url.rsplit("=", 1)[-1]
        if video_id not in self.videos:
            raise LookupError(f"ERROR: [youtube] {video_id}: Video unavailable")
        return dict(self.videos[video_id])

    def download(
        self, info: Mapping[str, Any], folder: Path, hook: Callable[[Mapping[str, Any]], None]
    ) -> Path:
        video_id = str(info["id"])
        self._record(f"download {video_id}")
        self._maybe_raise(f"download:{video_id}")
        target = folder / f"{video_id}.{info.get('ext', 'm4a')}"
        partial = target.with_name(target.name + ".part")
        written = 0
        with partial.open("wb") as file:
            index = 0
            while written < self.audio_size:
                size = min(self.chunk_size, self.audio_size - written)
                file.write(bytes(size))
                written += size
                status: dict[str, Any] = {"status": "downloading", "downloaded_bytes": written}
                if self.report_total:
                    status["total_bytes"] = self.audio_size
                else:
                    status["total_bytes_estimate"] = self.audio_size * 1.1
                hook(status)
                if self.on_chunk is not None:
                    self.on_chunk(index)
                index += 1
        partial.replace(target)
        hook({"status": "finished", "downloaded_bytes": written, "total_bytes": written})
        return target

    def fetch(self, url: str, max_bytes: int) -> bytes:
        self._record(f"fetch {url}")
        self._maybe_raise(url)
        data = self.thumbnails[url]
        if len(data) > max_bytes:
            raise ValueError(f"more than {max_bytes} bytes")
        return data

    def _record(self, call: str) -> None:
        with self._lock:
            self.calls.append(call)

    def _maybe_raise(self, key: str) -> None:
        error = self.errors.get(key)
        if error is not None:
            raise error
