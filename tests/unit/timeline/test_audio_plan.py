"""B2 · Audio plan: songs back to back, trims, fades, final fade and silence (§1.7)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from passi.model import defaults
from passi.model.types import Fade, Song
from passi.timeline import Timeline, compute_timeline
from tests.unit.timeline.helpers import make_project, make_song

MICRO = defaults.CUT_MICRO_FADE_S


def plan_for(photo_durations: list[float], songs: list[Song]) -> Timeline:
    return compute_timeline(make_project(photo_durations, songs=songs))


def test_songs_play_back_to_back_with_their_trims() -> None:
    songs = [make_song(0, 10.0, trim_start_s=2.0, trim_end_s=6.0), make_song(1, 5.0, trim_start_s=1.0)]
    timeline = plan_for([3.0] * 4, songs)
    first, second = timeline.audio_plan.segments
    assert (first.song_id, first.video_start, first.video_end, first.source_start) == ("s0", 0.0, 4.0, 2.0)
    assert (second.song_id, second.video_start, second.video_end, second.source_start) == (
        "s1",
        4.0,
        8.0,
        1.0,
    )
    assert timeline.music_duration_s == 8.0


def test_music_shorter_than_the_show_is_followed_by_silence() -> None:
    timeline = plan_for([3.0] * 4, [make_song(0, 7.0)])
    (segment,) = timeline.audio_plan.segments
    assert segment.video_end == 7.0
    assert (segment.fade_in_s, segment.fade_out_s) == (1.0, 3.0)
    assert timeline.audio_plan.final_fade is None


def test_music_longer_than_the_show_ends_with_a_final_fade_at_the_end_of_the_video() -> None:
    timeline = plan_for([2.0] * 5, [make_song(0, 6.0), make_song(1, 30.0), make_song(2, 30.0)])
    plan = timeline.audio_plan
    assert [s.song_id for s in plan.segments] == ["s0", "s1"]
    assert plan.segments[-1].video_end == 10.0
    assert plan.segments[-1].fade_out_s == 0.0  # the final fade takes over
    assert plan.segments[0].fade_out_s == 3.0  # the first song ends normally
    assert plan.final_fade is not None
    assert (plan.final_fade.start, plan.final_fade.end) == (10.0 - defaults.MUSIC_FINAL_FADE_S, 10.0)
    assert plan.final_fade.end == timeline.total_duration_s
    assert timeline.music_duration_s == 66.0


def test_final_fade_is_clipped_to_very_short_shows() -> None:
    timeline = plan_for([1.0, 1.0], [make_song(0, 60.0)])
    final = timeline.audio_plan.final_fade
    assert final is not None and (final.start, final.end) == (0.0, 2.0)


def test_music_that_fits_within_half_a_frame_needs_no_final_fade() -> None:
    timeline = plan_for([2.0] * 3, [make_song(0, 6.0 + 0.4 / 30)])
    (segment,) = timeline.audio_plan.segments
    assert timeline.audio_plan.final_fade is None
    assert segment.video_end == 6.0 and segment.fade_out_s == 3.0


def test_disabled_fades_keep_the_anti_click_fade() -> None:
    song = make_song(0, 20.0, fade_in=Fade(False, 1.0), fade_out=Fade(False, 3.0))
    (segment,) = plan_for([2.0] * 10, [song]).audio_plan.segments
    assert (segment.fade_in_s, segment.fade_out_s) == (MICRO, MICRO)
    zero = make_song(0, 20.0, fade_in=Fade(True, 0.0), fade_out=Fade(True, 0.0))
    (segment,) = plan_for([2.0] * 10, [zero]).audio_plan.segments
    assert (segment.fade_in_s, segment.fade_out_s) == (MICRO, MICRO)


def test_song_shorter_than_its_two_fades_reduces_each_fade_to_40_percent() -> None:
    song = make_song(0, 3.0, fade_in=Fade(True, 2.0), fade_out=Fade(True, 3.0))
    (segment,) = plan_for([2.0] * 5, [song]).audio_plan.segments
    assert segment.fade_in_s == pytest.approx(1.2)
    assert segment.fade_out_s == pytest.approx(1.2)


def test_empty_songs_are_left_out_of_the_mix() -> None:
    songs = [make_song(0, 0.0), make_song(1, 10.0, trim_start_s=10.0), make_song(2, 4.0)]
    timeline = plan_for([2.0] * 4, songs)
    assert [s.song_id for s in timeline.audio_plan.segments] == ["s2"]
    assert timeline.music_duration_s == 4.0


def test_trim_end_beyond_the_file_is_limited_to_the_file() -> None:
    timeline = plan_for([2.0] * 10, [make_song(0, 5.0, trim_end_s=9.0)])
    assert timeline.music_duration_s == 5.0


def test_no_photos_means_no_segments_but_the_music_length_is_known() -> None:
    timeline = plan_for([], [make_song(0, 30.0)])
    assert timeline.audio_plan.segments == () and timeline.audio_plan.final_fade is None
    assert timeline.music_duration_s == 30.0


song_lists = st.lists(
    st.builds(
        lambda length, start, end, fi, fo: (length, start, end, fi, fo),
        st.floats(0.0, 400.0),
        st.floats(0.0, 50.0),
        st.one_of(st.none(), st.floats(0.0, 400.0)),
        st.tuples(st.booleans(), st.floats(0.0, 10.0)),
        st.tuples(st.booleans(), st.floats(0.0, 10.0)),
    ),
    max_size=6,
)


@given(st.lists(st.floats(1.0, 30.0), max_size=30), song_lists)
def test_segments_are_consecutive_inside_the_video_and_fades_fit(
    photos: list[float], raw: list[tuple[float, float, float | None, tuple[bool, float], tuple[bool, float]]]
) -> None:
    songs = [
        make_song(i, length, trim_start_s=start, trim_end_s=end, fade_in=Fade(*fi), fade_out=Fade(*fo))
        for i, (length, start, end, fi, fo) in enumerate(raw)
    ]
    timeline = plan_for(photos, songs)
    total = timeline.total_duration_s
    plan = timeline.audio_plan
    position = 0.0
    for segment in plan.segments:
        assert segment.video_start == pytest.approx(position, abs=1e-9)
        assert 0.0 <= segment.video_start < segment.video_end <= total
        length = segment.video_end - segment.video_start
        assert segment.fade_in_s >= 0 and segment.fade_out_s >= 0
        assert segment.fade_in_s + segment.fade_out_s <= length + 1e-9
        position = segment.video_end
    played = sum(s.video_end - s.video_start for s in plan.segments)
    assert played == pytest.approx(min(total, timeline.music_duration_s), abs=1e-6)
    if plan.final_fade is not None:
        assert plan.final_fade.end == total
        assert timeline.music_duration_s > total
