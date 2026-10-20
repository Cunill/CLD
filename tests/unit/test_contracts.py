"""B0: the contracts exist, have the documented defaults and are not yet implemented."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from passi import cli
from passi.model import defaults
from passi.model.types import FitMode, MotionType, OutputFormat, Photo, Project, Song


def test_project_defaults_match_specification() -> None:
    project = Project()
    assert project.output_format is OutputFormat.HORIZONTAL
    assert project.default_duration_s == 2.0
    assert project.crossfade_s == 1.0
    assert project.fade_from_black_s == 1.0
    assert project.fade_to_black_s == 2.0
    assert (project.zoom_amount, project.pan_amount) == (0.09, 0.09)
    assert project.motion_enabled
    assert project.music.normalize
    assert not project.music.keep_fitted
    assert project.music.master_volume == 1.0


def test_song_defaults_match_specification() -> None:
    song = Song("s1", Path("a.mp3"), None, 180.0)
    assert song.fade_in.enabled and song.fade_in.seconds == 1.0
    assert song.fade_out.enabled and song.fade_out.seconds == 3.0
    assert song.volume == 1.0
    assert song.trim_start_s == 0.0 and song.trim_end_s is None


def test_every_default_is_inside_its_range() -> None:
    pairs = [
        (defaults.PHOTO_DURATION_S, defaults.PHOTO_DURATION_RANGE),
        (defaults.CROSSFADE_S, defaults.CROSSFADE_RANGE),
        (defaults.FADE_FROM_BLACK_S, defaults.BLACK_FADE_RANGE),
        (defaults.FADE_TO_BLACK_S, defaults.BLACK_FADE_RANGE),
        (defaults.ZOOM_AMOUNT, defaults.MOTION_AMOUNT_RANGE),
        (defaults.PAN_AMOUNT, defaults.MOTION_AMOUNT_RANGE),
        (defaults.SONG_FADE_IN_S, defaults.SONG_FADE_RANGE),
        (defaults.SONG_FADE_OUT_S, defaults.SONG_FADE_RANGE),
        (defaults.MASTER_VOLUME, defaults.MASTER_VOLUME_RANGE),
        (defaults.SONG_VOLUME, defaults.SONG_VOLUME_RANGE),
    ]
    for value, allowed in pairs:
        assert allowed.minimum <= value <= allowed.maximum
        assert allowed.clamp(value) == value
    assert defaults.PHOTO_DURATION_RANGE.clamp(99) == 3.0


def test_output_sizes_are_full_hd() -> None:
    assert OutputFormat.HORIZONTAL.size == (1920, 1080)
    assert OutputFormat.VERTICAL.size == (1080, 1920)


def test_photo_duration_falls_back_to_project_default() -> None:
    photo = Photo("p1", Path("a.jpg"), None, 4000, 3000)
    project = Project(photos=(photo,))
    assert project.photo_duration(photo) == 2.0
    custom = Photo("p2", Path("b.jpg"), None, 4000, 3000, duration_s=2.5)
    assert project.photo_duration(custom) == 2.5
    assert photo.fit is FitMode.AUTO
    assert photo.motion.type is MotionType.NONE


def test_motion_probabilities_sum_to_one() -> None:
    from passi.motion import BASE_PROBABILITIES

    assert abs(sum(BASE_PROBABILITIES.values()) - 1.0) < 1e-9


def _stubs() -> list[tuple[str, Callable[[], Any]]]:
    from passi import audio, ffmpeg, importer, timeline

    p = Path("x")
    return [
        ("B4 import", lambda: importer.import_paths([p])),
        ("B7 probe", lambda: ffmpeg.probe(p)),
        ("B8 audio", lambda: audio.prepare(Project(), timeline.AudioPlan((), None), p)),
    ]


@pytest.mark.parametrize(("label", "call"), _stubs(), ids=[s[0] for s in _stubs()])
def test_stubs_are_not_implemented_yet(label: str, call: Callable[[], Any]) -> None:
    with pytest.raises(NotImplementedError):
        call()


def test_cli_parsers_define_the_documented_arguments() -> None:
    args = cli.build_new_parser().parse_args(["fotos", "a.mp3", "b.mp3", "-o", "p.passi", "--vertical"])
    assert args.photos_dir == Path("fotos")
    assert args.music == [Path("a.mp3"), Path("b.mp3")]
    assert args.vertical
    args = cli.build_render_parser().parse_args(["p.passi", "v.mp4"])
    assert args.output == Path("v.mp4")
    assert cli.main_render(["p.passi", "v.mp4"]) == cli.EXIT_NOT_IMPLEMENTED
