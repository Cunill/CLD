"""B2 · Fit to music (§1.7, decision 0005: 1-3 s per photo)."""

from __future__ import annotations

import itertools
import math
import time

import pytest
from hypothesis import given
from hypothesis import strategies as st

from passi.timeline import DEFAULT_DURATION_LIMITS, DurationLimits, fit_to_music

FRAME = 1 / 30


@given(st.lists(st.floats(1.0, 3.0), min_size=1, max_size=200), st.floats(0.0, 1.0))
def test_reachable_target_is_met_within_one_frame_and_inside_the_limits(
    durations: list[float], position: float
) -> None:
    count = len(durations)
    target = count * (1.0 + 2.0 * position)  # anywhere between n * 1 s and n * 3 s
    result = fit_to_music(durations, target)
    assert len(result.durations) == count
    assert abs(math.fsum(result.durations) - target) <= FRAME
    assert result.achieved_total_s == pytest.approx(math.fsum(result.durations))
    assert all(1.0 <= d <= 3.0 for d in result.durations)
    assert not result.warning


@given(st.lists(st.floats(1.0, 3.0), min_size=2, max_size=100), st.floats(0.0, 1.0))
def test_proportions_are_kept_between_photos_that_do_not_hit_a_limit(
    durations: list[float], position: float
) -> None:
    target = len(durations) * (1.0 + 2.0 * position)
    result = fit_to_music(durations, target)
    free = [(d, f) for d, f in zip(durations, result.durations, strict=True) if 1.0 + 1e-9 < f < 3.0 - 1e-9]
    if len(free) >= 2:
        ratios = [f / d for d, f in free]
        assert max(ratios) == pytest.approx(min(ratios), rel=1e-9)
    # Order is preserved: a longer photo never ends up shorter.
    pairs = sorted(zip(durations, result.durations, strict=True))
    assert all(a[1] <= b[1] + 1e-12 for a, b in itertools.pairwise(pairs))


def test_a_photo_twice_as_long_stays_twice_as_long() -> None:
    result = fit_to_music([1.0, 2.0, 1.0], 6.0)
    assert result.durations == pytest.approx((1.5, 3.0, 1.5))


def test_photos_held_at_a_limit_let_the_others_absorb_the_difference() -> None:
    result = fit_to_music([1.0, 1.0, 3.0], 7.5)
    assert result.durations == pytest.approx((2.25, 2.25, 3.0))
    result = fit_to_music([1.0, 3.0, 3.0], 3.5)
    assert result.durations == pytest.approx((1.0, 1.25, 1.25))


def test_too_many_photos_for_the_music_warns_and_clamps_to_the_minimum() -> None:
    result = fit_to_music([2.0] * 10, 6.0)  # 0.6 s per photo
    assert result.warning
    assert result.durations == (1.0,) * 10
    assert result.achieved_total_s == 10.0 > 6.0


def test_music_too_long_for_the_photos_warns_and_clamps_to_the_maximum() -> None:
    result = fit_to_music([2.0] * 10, 45.0)
    assert result.warning
    assert result.durations == (3.0,) * 10
    assert result.achieved_total_s == 30.0 < 45.0


def test_warning_threshold_is_independent_of_the_minimum() -> None:
    limits = DurationLimits(minimum=1.0, maximum=30.0, warn_below=2.0)
    soft = fit_to_music([5.0] * 4, 6.0, limits)  # 1.5 s each: allowed, but below 2 s
    assert soft.warning and soft.durations == pytest.approx((1.5,) * 4)
    fine = fit_to_music([5.0] * 4, 40.0, limits)
    assert not fine.warning and fine.durations == pytest.approx((10.0,) * 4)


def test_degenerate_inputs() -> None:
    assert fit_to_music([], 10.0).durations == ()
    assert not fit_to_music([], 10.0).warning
    zeros = fit_to_music([0.0, 0.0], 4.0)
    assert zeros.durations == pytest.approx((2.0, 2.0))


def test_default_limits_are_those_of_decision_0005() -> None:
    assert (DEFAULT_DURATION_LIMITS.minimum, DEFAULT_DURATION_LIMITS.maximum) == (1.0, 3.0)
    assert DEFAULT_DURATION_LIMITS.warn_below == 1.0


def test_a_thousand_photos_fit_quickly() -> None:
    durations = [1.0 + (i % 21) / 10 for i in range(1000)]
    start = time.perf_counter()
    result = fit_to_music(durations, 2345.6)
    assert time.perf_counter() - start < 1.0
    assert abs(result.achieved_total_s - 2345.6) <= FRAME


@given(st.lists(st.floats(1.0, 3.0), min_size=1, max_size=60), st.floats(0.0, 1.0))
def test_fitted_show_lasts_as_long_as_the_music_to_the_frame(durations: list[float], position: float) -> None:
    from passi.timeline import compute_timeline
    from tests.unit.timeline.helpers import make_project, make_song

    music_s = len(durations) * (1.0 + 2.0 * position)
    fitted = fit_to_music(durations, music_s).durations
    timeline = compute_timeline(make_project(list(fitted), songs=[make_song(0, music_s)]))
    assert abs(timeline.total_frames - round(timeline.music_duration_s * 30)) <= 1
    assert timeline.audio_plan.final_fade is None
