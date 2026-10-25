"""C03: the options YtDlpBackend gives yt-dlp, with a fake YoutubeDL (no network).

Stereo audio first (docs/sessions/C02.md: with Deno, plain "bestaudio" chose a 5.1 AAC of 388 kbps
when a stereo Opus of 129 kbps was there).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from passimaker.youtube.backend import AUDIO_FORMAT, INFO_FORMAT, YtDlpBackend

ID = "aqz-KE-bpKQ"


class FakeYoutubeDL:
    """Records the options and answers like yt-dlp's YoutubeDL."""

    created: list[dict[str, Any]] = []  # noqa: RUF012

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options
        FakeYoutubeDL.created.append(options)

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def extract_info(self, url: str, download: bool) -> dict[str, Any]:
        return {"id": ID, "webpage_url": url}

    def sanitize_info(self, info: dict[str, Any]) -> dict[str, Any]:
        return info

    def process_ie_result(self, info: dict[str, Any], download: bool) -> dict[str, Any]:
        folder = Path(self.options["outtmpl"]).parent
        path = folder / f"{info['id']}.webm"
        path.write_bytes(b"opus")
        return {**info, "requested_downloads": [{"filepath": str(path)}]}


@pytest.fixture
def fake_ydl(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    FakeYoutubeDL.created = []
    monkeypatch.setattr(YtDlpBackend, "_ydl", staticmethod(FakeYoutubeDL))
    return FakeYoutubeDL.created


def test_stereo_is_asked_before_the_best_audio(fake_ydl: list[dict[str, Any]], tmp_path: Path) -> None:
    real = YtDlpBackend()
    info = real.extract_info(f"https://www.youtube.com/watch?v={ID}", flat=False)
    path = real.download(info, tmp_path, lambda status: None)
    assert path == tmp_path / f"{ID}.webm"
    assert len(fake_ydl) == 2
    reading, downloading = fake_ydl
    assert downloading["format"] == "bestaudio[audio_channels<=?2]/bestaudio" == AUDIO_FORMAT
    assert reading["format"] == AUDIO_FORMAT + "/best" == INFO_FORMAT  # only to read the data
    for options in fake_ydl:
        assert options["postprocessors"] == [] and options["fixup"] == "never"


def test_search_reads_flat(fake_ydl: list[dict[str, Any]]) -> None:
    YtDlpBackend().extract_info("ytsearch10:x", flat=True)
    assert fake_ydl[0]["extract_flat"] == "in_playlist" and fake_ydl[0]["format"] == INFO_FORMAT


def _formats(*specs: tuple[str, str, int | None, float]) -> list[dict[str, Any]]:
    """(format_id, acodec, audio_channels, abr) → audio-only formats as YouTube lists them."""
    formats: list[dict[str, Any]] = []
    for format_id, acodec, channels, abr in specs:
        item: dict[str, Any] = {
            "format_id": format_id,
            "url": f"https://example.invalid/{format_id}",
            "ext": "m4a" if acodec.startswith("mp4a") else "webm",
            "acodec": acodec,
            "vcodec": "none",
            "abr": abr,
            "tbr": abr,
            "protocol": "https",
        }
        if channels is not None:
            item["audio_channels"] = channels
        formats.append(item)
    return formats


def _chosen(formats: list[dict[str, Any]], spec: str = AUDIO_FORMAT) -> str | None:
    """yt-dlp's own format selector applied to `spec` (no network); None if nothing matches."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        selector = ydl.build_format_selector(spec)
        chosen = list(selector({"formats": formats, "has_merged_format": False, "incomplete_formats": False}))
    return str(chosen[0]["format_id"]) if chosen else None


def test_yt_dlp_picks_the_stereo_opus_before_the_5_1_aac() -> None:
    """The case of the C02 test on the user's PC."""
    formats = _formats(
        ("140", "mp4a.40.2", 2, 129.0), ("251", "opus", 2, 129.5), ("258", "mp4a.40.2", 6, 388.0)
    )
    assert _chosen(formats) == "251"


def test_formats_without_a_channel_count_are_accepted() -> None:
    assert _chosen(_formats(("258", "mp4a.40.2", 6, 388.0), ("x", "opus", None, 160.0))) == "x"


def test_without_stereo_the_best_audio_is_kept() -> None:
    assert _chosen(_formats(("256", "mp4a.40.5", 6, 192.0), ("258", "mp4a.40.2", 6, 388.0))) == "258"


def test_a_live_stream_can_be_read_but_not_downloaded() -> None:
    """A live stream has only formats with video and audio together (HLS): reading its data must
    work, so download_audio refuses it as a live stream (ERROR_LIVE), not as "YouTube ha canviat"."""
    live = [
        {
            "format_id": "95",
            "url": "https://example.invalid/95.m3u8",
            "ext": "mp4",
            "acodec": "mp4a.40.2",
            "vcodec": "avc1.4d401f",
            "protocol": "m3u8_native",
            "tbr": 1500.0,
        }
    ]
    assert _chosen(live, INFO_FORMAT) == "95"
    assert _chosen(live, AUDIO_FORMAT) is None
