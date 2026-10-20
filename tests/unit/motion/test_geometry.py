"""B3 · Window interpolation and the "no edges" guarantee of window_at."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from passi.model.types import FitMode, MotionType, OutputFormat, PhotoMotion, ResolvedFit, Window
from passi.motion import is_inside, resolve_fit, window_at, window_rect

H = OutputFormat.HORIZONTAL


def motion(start: Window, end: Window) -> PhotoMotion:
    return PhotoMotion(type=MotionType.COMBINED, start=start, end=end, resolved_fit=ResolvedFit.FILL)


def test_window_at_endpoints_and_clamping() -> None:
    m = motion(Window(0.4, 0.5, 1.0), Window(0.6, 0.45, 1.2))
    assert window_at(m, 0.0) == m.start
    assert window_at(m, 1.0) == pytest.approx(m.end)
    assert window_at(m, -1.0) == m.start
    assert window_at(m, 2.0) == pytest.approx(m.end)


def test_centre_is_linear_and_scale_is_geometric() -> None:
    m = motion(Window(0.4, 0.5, 1.0), Window(0.6, 0.45, 1.21))
    mid = window_at(m, 0.5)
    assert mid.centre_x == pytest.approx(0.5)
    assert mid.centre_y == pytest.approx(0.475)
    assert mid.scale == pytest.approx(1.1)  # sqrt(1.21): constant apparent zoom speed
    ratios = [window_at(m, (i + 1) / 10).scale / window_at(m, i / 10).scale for i in range(10)]
    assert max(ratios) - min(ratios) < 1e-12


def _random_inside(draw: st.DrawFn, base: tuple[float, float]) -> Window:
    scale = draw(st.floats(1.0, 3.0))
    wx, wy = base[0] / scale, base[1] / scale
    cx = draw(st.floats(wx / 2, 1 - wx / 2)) if wx < 1 else 0.5
    cy = draw(st.floats(wy / 2, 1 - wy / 2)) if wy < 1 else 0.5
    return Window(cx, cy, scale)


@st.composite
def inside_motions(draw: st.DrawFn) -> tuple[tuple[float, float], PhotoMotion]:
    bx = draw(st.floats(0.2, 1.0))
    by = draw(st.floats(0.2, 1.0))
    if draw(st.booleans()):
        bx = 1.0
    else:
        by = 1.0
    base = (bx, by)
    return base, motion(_random_inside(draw, base), _random_inside(draw, base))


@settings(max_examples=2000, deadline=None)
@given(inside_motions())
def test_every_intermediate_window_is_inside_if_the_ends_are(
    case: tuple[tuple[float, float], PhotoMotion],
) -> None:
    base, m = case
    assert is_inside(m.start, base) and is_inside(m.end, base)
    for p in np.linspace(0.0, 1.0, 201):
        assert is_inside(window_at(m, float(p)), base, tolerance=1e-9)


def test_is_inside() -> None:
    base = (1.0, 0.75)
    assert is_inside(Window(0.5, 0.5, 1.0), base)
    assert is_inside(Window(0.5, 0.375, 1.0), base)  # touching the top edge
    assert not is_inside(Window(0.5, 0.3, 1.0), base)
    assert not is_inside(Window(0.5, 0.5, 0.9), base)  # larger than the scale-1 window


def test_window_rect_in_canvas_pixels() -> None:
    fit = resolve_fit(4000, 3000, H, FitMode.AUTO)
    left, top, right, bottom = window_rect(Window(0.5, 0.5, 1.0), fit, H)
    assert (left, right) == pytest.approx((0.0, 4000.0))
    assert bottom - top == pytest.approx(2250.0)  # 4000 * 9 / 16
    left, top, right, bottom = window_rect(Window(0.5, 0.5, 2.0), fit, H)
    assert right - left == pytest.approx(2000.0)
    assert math.isclose((right - left) / (bottom - top), 16 / 9)
