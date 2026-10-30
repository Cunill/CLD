"""B2 · Fit to music (§1.7). M07: durations set by hand are fixed, limits 0.4-24 s (decision 0014)."""

from __future__ import annotations

import itertools
import math
import time

import pytest
from hypothesis import given
from hypothesis import strategies as st

from passimaker.timeline import DEFAULT_DURATION_LIMITS, DurationLimits, fit_to_music
from passimaker.timeline.types import FitBlock

FRAME = 1 / 30
LIMITS_1_3 = DurationLimits(minimum=1.0, maximum=3.0, warn_below=1.0)
"""The limits of decision 0005, passed explicitly: the algorithm works with any limits."""


@given(st.lists(st.floats(1.0, 3.0), min_size=1, max_size=200), st.floats(0.0, 1.0))
def test_reachable_target_is_met_within_one_frame_and_inside_the_limits(
    durations: list[float], position: float
) -> None:
    count = len(durations)
    target = count * (1.0 + 2.0 * position)  # anywhere between n * 1 s and n * 3 s
    result = fit_to_music(durations, target, LIMITS_1_3)
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
    result = fit_to_music(durations, target, LIMITS_1_3)
    free = [(d, f) for d, f in zip(durations, result.durations, strict=True) if 1.0 + 1e-9 < f < 3.0 - 1e-9]
    if len(free) >= 2:
        ratios = [f / d for d, f in free]
        assert max(ratios) == pytest.approx(min(ratios), rel=1e-9)
    # Order is preserved: a longer photo never ends up shorter.
    pairs = sorted(zip(durations, result.durations, strict=True))
    assert all(a[1] <= b[1] + 1e-12 for a, b in itertools.pairwise(pairs))


def test_a_photo_twice_as_long_stays_twice_as_long() -> None:
    result = fit_to_music([1.0, 2.0, 1.0], 6.0, LIMITS_1_3)
    assert result.durations == pytest.approx((1.5, 3.0, 1.5))


def test_photos_held_at_a_limit_let_the_others_absorb_the_difference() -> None:
    result = fit_to_music([1.0, 1.0, 3.0], 7.5, LIMITS_1_3)
    assert result.durations == pytest.approx((2.25, 2.25, 3.0))
    result = fit_to_music([1.0, 3.0, 3.0], 3.5, LIMITS_1_3)
    assert result.durations == pytest.approx((1.0, 1.25, 1.25))


def test_too_many_photos_for_the_music_warns_and_clamps_to_the_minimum() -> None:
    result = fit_to_music([2.0] * 10, 6.0, LIMITS_1_3)  # 0.6 s per photo
    assert result.warning
    assert result.durations == (1.0,) * 10
    assert result.achieved_total_s == 10.0 > 6.0


def test_music_too_long_for_the_photos_warns_and_clamps_to_the_maximum() -> None:
    result = fit_to_music([2.0] * 10, 45.0, LIMITS_1_3)
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


def test_default_limits_are_those_of_decision_0014() -> None:
    assert (DEFAULT_DURATION_LIMITS.minimum, DEFAULT_DURATION_LIMITS.maximum) == (0.4, 24.0)
    assert DEFAULT_DURATION_LIMITS.warn_below == 0.4


def test_with_the_default_limits_a_photo_may_last_up_to_24_s_or_as_little_as_0_4_s() -> None:
    assert fit_to_music([2.0] * 3, 60.0).durations == pytest.approx((20.0,) * 3)
    assert fit_to_music([2.0] * 3, 1.5).durations == pytest.approx((0.5,) * 3)
    assert not fit_to_music([2.0] * 3, 1.5).warning
    assert fit_to_music([2.0] * 10, 3.0).warning  # 0.3 s each


def test_a_thousand_photos_fit_quickly() -> None:
    durations = [1.0 + (i % 21) / 10 for i in range(1000)]
    start = time.perf_counter()
    result = fit_to_music(durations, 2345.6)
    assert time.perf_counter() - start < 1.0
    assert abs(result.achieved_total_s - 2345.6) <= FRAME


@given(st.lists(st.floats(1.0, 3.0), min_size=1, max_size=60), st.floats(0.0, 1.0))
def test_fitted_show_lasts_as_long_as_the_music_to_the_frame(durations: list[float], position: float) -> None:
    from passimaker.timeline import compute_timeline
    from tests.unit.timeline.helpers import make_project, make_song

    music_s = len(durations) * (1.0 + 2.0 * position)
    fitted = fit_to_music(durations, music_s).durations
    timeline = compute_timeline(make_project(list(fitted), songs=[make_song(0, music_s)]))
    assert abs(timeline.total_frames - round(timeline.music_duration_s * 30)) <= 1
    assert timeline.audio_plan.final_fade is None


# --- Fixed durations (M07, decision 0014) ----------------------------------------------------------


@given(
    st.lists(st.tuples(st.floats(0.4, 24.0), st.booleans()), min_size=1, max_size=100),
    st.floats(0.001, 0.999),  # away from the limits, where rounding of the sums could tip the warning
)
def test_fixed_durations_never_change_and_the_total_reaches_the_music_when_it_can(
    items: list[tuple[float, bool]], position: float
) -> None:
    durations = [d for d, _ in items]
    fixed = [f for _, f in items]
    free = fixed.count(False)
    fixed_total = math.fsum(d for d, f in items if f)
    low, high = DEFAULT_DURATION_LIMITS.minimum, DEFAULT_DURATION_LIMITS.maximum
    # With free photos, anywhere they can reach.
    target = fixed_total + (free * (low + (high - low) * position) if free else 5.0)
    result = fit_to_music(durations, target, fixed=fixed)
    assert len(result.durations) == len(durations)
    for d, f, out in zip(durations, fixed, result.durations, strict=True):
        if f:
            assert out == d
        else:
            assert low <= out <= high
    if free == 0:
        assert result.blocked is FitBlock.ALL_FIXED
        assert result.durations == tuple(durations)
    else:
        assert result.blocked is None
        assert abs(math.fsum(result.durations) - target) <= FRAME
        assert not result.warning


@given(st.lists(st.floats(0.4, 24.0), min_size=2, max_size=60), st.integers(0, 2**32), st.floats(0.0, 1.0))
def test_proportions_are_kept_between_the_free_photos(
    durations: list[float], seed: int, position: float
) -> None:
    import random

    rng = random.Random(seed)
    fixed = [rng.random() < 0.4 for _ in durations]
    free_idx = [i for i, f in enumerate(fixed) if not f]
    if len(free_idx) < 2:
        return
    fixed_total = math.fsum(d for d, f in zip(durations, fixed, strict=True) if f)
    target = fixed_total + len(free_idx) * (1.0 + 4.0 * position)
    result = fit_to_music(durations, target, fixed=fixed)
    low, high = DEFAULT_DURATION_LIMITS.minimum, DEFAULT_DURATION_LIMITS.maximum
    ratios = [
        result.durations[i] / durations[i] for i in free_idx if low + 1e-9 < result.durations[i] < high - 1e-9
    ]
    if len(ratios) >= 2:
        assert max(ratios) == pytest.approx(min(ratios), rel=1e-9)


def test_the_fixed_durations_are_subtracted_from_the_music_and_the_rest_is_shared() -> None:
    # 10 s fixed in the middle, music 40 s: the other three share 30 s in the proportion 1:2:3.
    result = fit_to_music([1.0, 10.0, 2.0, 3.0], 40.0, fixed=[False, True, False, False])
    assert result.durations == pytest.approx((5.0, 10.0, 10.0, 15.0))
    assert not result.warning and result.blocked is None


def test_free_photos_held_at_a_limit_let_the_other_free_ones_absorb_the_difference() -> None:
    result = fit_to_music([1.0, 1.0, 3.0, 9.0], 15.0, LIMITS_1_3, fixed=[False, False, False, True])
    assert result.durations == pytest.approx(
        (1.5, 1.5, 3.0, 9.0)
    )  # 6 s left: the 3 s photo is held at its limit
    assert math.fsum(result.durations) == pytest.approx(15.0)


def test_all_fixed_changes_nothing_and_says_so() -> None:
    result = fit_to_music([3.0, 5.0], 20.0, fixed=[True, True])
    assert result.durations == (3.0, 5.0)
    assert result.blocked is FitBlock.ALL_FIXED and result.warning
    assert result.achieved_total_s == 8.0


def test_music_that_does_not_cover_the_fixed_durations_changes_nothing_and_says_so() -> None:
    for music in (8.0, 5.0):
        result = fit_to_music([3.0, 5.0, 2.0], music, fixed=[True, True, False])
        assert result.durations == (3.0, 5.0, 2.0)
        assert result.blocked is FitBlock.FIXED_TOO_LONG and result.warning
        assert result.achieved_total_s == 10.0


def test_free_photos_that_cannot_reach_the_target_are_clamped_and_warn() -> None:
    result = fit_to_music([2.0, 2.0, 7.0], 100.0, fixed=[False, False, True])
    assert result.durations == (24.0, 24.0, 7.0) and result.warning and result.blocked is None
    short = fit_to_music([2.0] * 10 + [5.0], 6.0, fixed=[False] * 10 + [True])  # 1 s left for 10 photos
    assert short.durations[:10] == (0.4,) * 10 and short.warning


def test_fixed_must_match_the_durations() -> None:
    with pytest.raises(ValueError, match="one flag"):
        fit_to_music([1.0, 2.0], 5.0, fixed=[True])


def test_photos_fitted_to_0_4_s_still_make_a_valid_timeline() -> None:
    from passimaker.timeline import compute_timeline
    from tests.unit.timeline.helpers import make_project, make_song

    fitted = fit_to_music([2.0] * 25, 10.0).durations  # 0.4 s each
    assert fitted == pytest.approx((0.4,) * 25)
    line = compute_timeline(make_project(list(fitted), songs=[make_song(0, 10.0)]))
    assert abs(line.total_frames - 300) <= 1
    assert all(s.visible_end > s.visible_start for s in line.slots)
    assert all(s.fade_in is None or s.fade_in.end - s.fade_in.start <= 0.4 for s in line.slots)
