"""C04: the parts of convert_to_mp3 that need no ffmpeg (arguments, progress lines, temporary name)."""

from __future__ import annotations

from pathlib import Path

import pytest

from passimaker import ffmpeg
from passimaker.ffmpeg import _mp3


def test_partial_file_is_next_to_the_destination() -> None:
    dest = Path("carpeta") / "Cançó 🎶.mp3"
    assert _mp3.partial_path(dest) == Path("carpeta") / "Cançó 🎶.mp3.part"


def test_only_non_empty_tags_become_arguments() -> None:
    assert _mp3._tag_args(ffmpeg.Mp3Tags()) == []
    tags = ffmpeg.Mp3Tags(title="-Títol=amb igual ☀️", artist="", comment="https://youtu.be/x")
    assert _mp3._tag_args(tags) == [
        "-metadata",
        "title=-Títol=amb igual ☀️",
        "-metadata",
        "comment=https://youtu.be/x",
    ]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("out_time_us=1500000", 1500),
        ("out_time_us=-23220", 0),
        ("out_time_us=N/A", None),
        ("out_time_ms=1500000", None),
        ("progress=continue", None),
        ("", None),
    ],
)
def test_progress_lines(line: str, expected: int | None) -> None:
    assert _mp3._parse_out_time_ms(line) == expected


@pytest.mark.parametrize("kbps", [0, 7, 321])
def test_bitrate_out_of_range(tmp_path: Path, kbps: int) -> None:
    with pytest.raises(ValueError):
        ffmpeg.convert_to_mp3(tmp_path / "a.wav", tmp_path / "a.mp3", kbps, ffmpeg.Mp3Tags())
