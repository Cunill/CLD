"""B2 · Time <-> frame conversion without accumulated error."""

from __future__ import annotations

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from passi.timeline import frame_to_time, time_to_frame

TWO_HOURS_FRAMES = 2 * 3600 * 30


def test_round_trip_over_a_two_hour_show() -> None:
    for frame in range(TWO_HOURS_FRAMES + 1):
        assert time_to_frame(frame_to_time(frame)) == frame


def test_no_accumulated_error_after_two_hours() -> None:
    t = frame_to_time(TWO_HOURS_FRAMES)
    assert t == 7200.0
    assert abs(Fraction(frame_to_time(TWO_HOURS_FRAMES - 1)) - Fraction(TWO_HOURS_FRAMES - 1, 30)) < Fraction(
        1, 10**9
    )


@given(st.integers(0, TWO_HOURS_FRAMES), st.floats(0.0, 0.999))
def test_any_instant_inside_a_frame_maps_to_that_frame(frame: int, fraction: float) -> None:
    t = (frame + fraction * 0.999) / 30
    assert time_to_frame(t) == frame


def test_other_frame_rates() -> None:
    assert frame_to_time(25, fps=25) == 1.0
    assert time_to_frame(1.0, fps=25) == 25
    assert time_to_frame(0.0399, fps=25) == 0
