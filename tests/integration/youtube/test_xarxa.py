"""C03: passimaker.youtube against the real YouTube (marker `xarxa`).

Never on the CI nor in the cloud (YouTube blocks those servers, and the cloud's proxy refuses it):
on the user's PC, with
    set PASSIMAKER_XARXA=1   (PowerShell: $env:PASSIMAKER_XARXA = "1")
    uv run pytest -m xarxa
Uses Big Buck Bunny (Blender Foundation, Creative Commons Attribution), the same video as the C02
spike, on the Blender channel since 2014.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from passimaker import ffmpeg, youtube
from passimaker.model import defaults
from passimaker.youtube.consent import ConsentToken

ID = "aqz-KE-bpKQ"

pytestmark = [
    pytest.mark.xarxa,
    pytest.mark.skipif(
        not os.environ.get("PASSIMAKER_XARXA"), reason="cal PASSIMAKER_XARXA=1 (PC de l'usuari)"
    ),
]


@pytest.fixture
def token() -> Iterator[ConsentToken]:
    yield youtube.consent.grant()
    youtube.consent.revoke()


def test_search(token: ConsentToken) -> None:
    first = youtube.search(token, "Big Buck Bunny Blender", limit=5)
    more = youtube.search(token, "Big Buck Bunny Blender", limit=5, offset=5)
    assert len(first) == 5 and len(more) == 5
    assert not {r.video_id for r in first} & {r.video_id for r in more}
    assert all(r.title and r.url == youtube.watch_url(r.video_id) for r in first)


def test_resolve_and_thumbnail(token: ConsentToken) -> None:
    result = youtube.resolve(token, youtube.parse_link(f"https://youtu.be/{ID}?t=30") or "")
    assert result.video_id == ID and "Big Buck Bunny" in result.title and not result.is_live
    assert result.duration_s is not None and 500 < result.duration_s < defaults.YOUTUBE_MAX_DURATION_S
    assert youtube.fetch_thumbnail(token, result.thumbnail_url)[:2] == b"\xff\xd8"  # JPEG


def test_download_and_convert(token: ConsentToken, tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []
    audio = youtube.download_audio(token, ID, tmp_path, progress=lambda d, t: calls.append((d, t)))
    assert audio.is_file() and calls[-1][0] == calls[-1][1]
    target = youtube.safe_target_path(tmp_path, "Big Buck Bunny")
    ffmpeg.convert_to_mp3(audio, target, defaults.YOUTUBE_MP3_BITRATE_KBPS, ffmpeg.Mp3Tags("Big Buck Bunny"))
    assert abs(ffmpeg.probe(target).duration_s - 596.5) < 2


def test_unavailable_video(token: ConsentToken) -> None:
    with pytest.raises(youtube.YoutubeUnavailableError):
        youtube.resolve(token, "aaaaaaaaaaa")
