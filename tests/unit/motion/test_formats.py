"""M10 · Fit and motion with the six output formats (Hypothesis): windows always inside 0-1."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from passimaker.model.types import FitMode, Intensity, MotionMode, MotionType, OutputFormat, ResolvedFit
from passimaker.motion import (
    base_window,
    draw_motions,
    is_inside,
    output_aspect,
    rebuild_motions,
    resolve_fit,
    window_at,
    window_rect,
)
from tests.unit.motion.helpers import base_of, request

PROGRESS = (0.0, 0.25, 0.5, 0.75, 1.0)
sides = st.integers(64, 12_000)
formats = st.sampled_from(OutputFormat)


@given(width=sides, height=sides, output_format=formats, preference=st.sampled_from(FitMode))
def test_the_canvas_holds_the_photo_and_a_window_of_the_video_shape(
    width: int, height: int, output_format: OutputFormat, preference: FitMode
) -> None:
    fit = resolve_fit(width, height, output_format, preference)
    base_x, base_y = base_window(fit.canvas_width, fit.canvas_height, output_format)
    assert 0 < base_x <= 1 and 0 < base_y <= 1 and max(base_x, base_y) == pytest.approx(1)
    window_aspect = base_x * fit.canvas_width / (base_y * fit.canvas_height)
    assert window_aspect == pytest.approx(output_aspect(output_format), rel=1e-9)
    if fit.fit is ResolvedFit.FILL:
        assert (fit.canvas_width, fit.canvas_height) == (width, height)
    else:
        assert fit.canvas_width >= width and fit.canvas_height >= height


@settings(max_examples=300)
@given(
    width=sides,
    height=sides,
    output_format=formats,
    preference=st.sampled_from(FitMode),
    manual=st.none() | st.sampled_from(MotionType),
    intensity=st.sampled_from(Intensity),
    duration=st.floats(0.4, 31.0),
    seed=st.integers(0, 2**31),
)
def test_every_window_is_inside_the_canvas_in_every_format(
    width: int,
    height: int,
    output_format: OutputFormat,
    preference: FitMode,
    manual: MotionType | None,
    intensity: Intensity,
    duration: float,
    seed: int,
) -> None:
    req = request(
        "p",
        width,
        height,
        output_format=output_format,
        fit=preference,
        duration=duration,
        mode=MotionMode.AUTO if manual is None else MotionMode.MANUAL,
        manual_type=manual,
    )
    motion = draw_motions([req], seed, intensity)["p"]
    base = base_of(req)
    for p in PROGRESS:
        window = window_at(motion, p)
        assert is_inside(window, base)
        left, top, right, bottom = window_rect(window, req.fit, output_format)
        tolerance = 1e-6 * max(req.fit.canvas_width, req.fit.canvas_height)
        assert -tolerance <= left < right <= req.fit.canvas_width + tolerance
        assert -tolerance <= top < bottom <= req.fit.canvas_height + tolerance
        assert (right - left) / (bottom - top) == pytest.approx(output_aspect(output_format), rel=1e-6)


@settings(max_examples=200)
@given(width=sides, height=sides, before=formats, after=formats, seed=st.integers(0, 2**31))
def test_changing_the_format_keeps_the_windows_inside(
    width: int, height: int, before: OutputFormat, after: OutputFormat, seed: int
) -> None:
    """The type is kept when it is still feasible (rebuild_motions); otherwise it is drawn again."""
    first = request("p", width, height, output_format=before)
    motion = draw_motions([first], seed, Intensity.MEDIUM)["p"]
    moved = request("p", width, height, output_format=after, current=motion)
    rebuilt = rebuild_motions([moved], seed, Intensity.MEDIUM)["p"]
    assert all(is_inside(window_at(rebuilt, p), base_of(moved)) for p in PROGRESS)


ZOOMS = (MotionType.ZOOM_IN, MotionType.ZOOM_OUT)


@settings(max_examples=200)
@given(
    width=st.integers(4000, 12_000),
    height=st.integers(4000, 12_000),
    before=formats,
    after=formats,
    zoom=st.sampled_from(ZOOMS),
    seed=st.integers(0, 2**31),
)
def test_a_zoom_on_a_large_photo_stays_a_zoom_in_every_format(
    width: int, height: int, before: OutputFormat, after: OutputFormat, zoom: MotionType, seed: int
) -> None:
    """Zooms are feasible with any fit when the photo is large, so the format change keeps them."""
    first = request("p", width, height, output_format=before, mode=MotionMode.MANUAL, manual_type=zoom)
    motion = draw_motions([first], seed, Intensity.MEDIUM)["p"]
    assert motion.type is zoom
    moved = request("p", width, height, output_format=after, current=replace(motion, mode=MotionMode.AUTO))
    assert rebuild_motions([moved], seed, Intensity.MEDIUM)["p"].type is zoom
