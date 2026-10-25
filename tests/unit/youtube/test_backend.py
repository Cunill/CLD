"""C03: the options YtDlpBackend gives yt-dlp, with a fake YoutubeDL (no network).

Stereo audio first (docs/sessions/C02.md: with Deno, plain "bestaudio" chose a 5.1 AAC of 388 kbps
when a stereo Opus of 129 kbps was there).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from passimaker.youtube.backend import AUDIO_FORMAT, YtDlpBackend

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
    for options in fake_ydl:
        assert options["format"] == "bestaudio[audio_channels<=?2]/bestaudio" == AUDIO_FORMAT
        assert options["postprocessors"] == [] and options["fixup"] == "never"


def test_search_uses_the_same_options_flat(fake_ydl: list[dict[str, Any]]) -> None:
    YtDlpBackend().extract_info("ytsearch10:x", flat=True)
    assert fake_ydl[0]["extract_flat"] == "in_playlist" and fake_ydl[0]["format"] == AUDIO_FORMAT


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


def _chosen(formats: list[dict[str, Any]]) -> str:
    """yt-dlp's own format selector applied to AUDIO_FORMAT (no network)."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        selector = ydl.build_format_selector(AUDIO_FORMAT)
        chosen = list(selector({"formats": formats, "has_merged_format": False, "incomplete_formats": False}))
    return str(chosen[0]["format_id"])


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
