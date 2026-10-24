"""photo_from_candidate: the rule shared by the interface and the command line (M05)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from passimaker.importer import PhotoCandidate, photo_from_candidate
from passimaker.model import OutputFormat


def candidate(width: int, height: int) -> PhotoCandidate:
    return PhotoCandidate(
        path=Path("foto.jpg"),
        width=width,
        height=height,
        exif_orientation=6,
        capture_time=datetime(2026, 10, 24, 12, 0),
        file_time=datetime(2026, 10, 24, 12, 5),
        color_profile=None,
    )


def test_the_photo_keeps_what_the_header_said() -> None:
    photo = photo_from_candidate(candidate(4000, 3000), "p1", OutputFormat.HORIZONTAL)
    assert (photo.id, photo.path, photo.width, photo.height) == ("p1", Path("foto.jpg"), 4000, 3000)
    assert photo.exif_orientation == 6
    assert photo.capture_time == datetime(2026, 10, 24, 12, 0)
    assert photo.relative_path is None
    assert photo.duration_s is None  # the project's general duration
    assert not photo.low_resolution


def test_a_short_side_under_half_the_video_is_low_resolution() -> None:
    # 1080p: half of the short side is 540 px.
    assert photo_from_candidate(candidate(800, 539), "p", OutputFormat.HORIZONTAL).low_resolution
    assert not photo_from_candidate(candidate(800, 540), "p", OutputFormat.HORIZONTAL).low_resolution
    assert photo_from_candidate(candidate(539, 800), "p", OutputFormat.VERTICAL).low_resolution
