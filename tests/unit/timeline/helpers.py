"""Builders and Hypothesis strategies for the timeline tests (no images, no audio)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from hypothesis import strategies as st

from passimaker.model.types import Fade, Music, Photo, Project, Song


def make_project(
    durations: Sequence[float | None],
    *,
    default_s: float = 2.0,
    crossfade_s: float = 1.0,
    fade_from_black_s: float = 1.0,
    fade_to_black_s: float = 2.0,
    songs: Sequence[Song] = (),
) -> Project:
    photos = tuple(
        Photo(f"p{i}", Path(f"foto_{i}.jpg"), None, 4000, 3000, duration_s=d) for i, d in enumerate(durations)
    )
    return Project(
        default_duration_s=default_s,
        crossfade_s=crossfade_s,
        fade_from_black_s=fade_from_black_s,
        fade_to_black_s=fade_to_black_s,
        slides=photos,
        music=Music(songs=tuple(songs)),
    )


def make_song(
    index: int,
    length_s: float,
    *,
    trim_start_s: float = 0.0,
    trim_end_s: float | None = None,
    fade_in: Fade | None = None,
    fade_out: Fade | None = None,
) -> Song:
    song = Song(f"s{index}", Path(f"cançó_{index}.mp3"), None, length_s, trim_start_s, trim_end_s)
    if fade_in is not None:
        song = Song(song.id, song.path, None, length_s, trim_start_s, trim_end_s, fade_in, song.fade_out)
    if fade_out is not None:
        song = Song(song.id, song.path, None, length_s, trim_start_s, trim_end_s, song.fade_in, fade_out)
    return song


durations_in_range = st.floats(1.0, 3.0, allow_nan=False)
"""The range the controller allows (decision 0005)."""
durations_wide = st.floats(0.1, 30.0, allow_nan=False)
"""Wider than the allowed range: the timeline must stay consistent anyway."""


@st.composite
def projects(draw: st.DrawFn, min_photos: int = 0, max_photos: int = 40, wide: bool = False) -> Project:
    duration = durations_wide if wide else durations_in_range
    durations = draw(st.lists(st.one_of(st.none(), duration), min_size=min_photos, max_size=max_photos))
    return make_project(
        durations,
        default_s=draw(duration),
        crossfade_s=draw(st.floats(0.0, 1.5) if not wide else st.floats(0.0, 10.0)),
        fade_from_black_s=draw(st.floats(0.0, 5.0)),
        fade_to_black_s=draw(st.floats(0.0, 5.0)),
    )
