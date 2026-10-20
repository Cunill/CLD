"""B3 · Speed limits, intensity and low-resolution photos (§1.5)."""

from __future__ import annotations

import numpy as np
import pytest

from passi.model.types import FitMode, Intensity, MotionMode, MotionType, OutputFormat
from passi.motion import (
    BLUR_INTENSITY_FACTOR,
    INTENSITY_PRESETS,
    MAX_UPSCALE,
    MotionAmounts,
    draw_motions,
    intensity_params,
    motion_speeds,
)
from tests.unit.motion.helpers import base_of, request

EPS = 1e-9


@pytest.mark.parametrize("intensity", list(Intensity))
@pytest.mark.parametrize("motion_type", [t for t in MotionType if t is not MotionType.NONE])
@pytest.mark.parametrize("duration", [1.0, 2.0, 3.5, 6.5, 15.0, 31.0])
def test_speed_never_exceeds_the_limits(
    intensity: Intensity, motion_type: MotionType, duration: float
) -> None:
    params = intensity_params(intensity)
    req = request("s", 4000, 3000, duration=duration, mode=MotionMode.MANUAL, manual_type=motion_type)
    motion = draw_motions([req], 1, intensity)["s"]
    zoom_speed, pan_speed = motion_speeds(motion, base_of(req), duration)
    assert zoom_speed <= params.max_zoom_speed + EPS
    assert pan_speed <= params.max_pan_speed + EPS


@pytest.mark.parametrize("intensity", list(Intensity))
def test_amounts_match_the_intensity_for_normal_durations(intensity: Intensity) -> None:
    params = intensity_params(intensity)
    zoom = draw_motions([request("z", mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_IN)], 1, intensity)[
        "z"
    ]
    assert zoom.end.scale / zoom.start.scale - 1 == pytest.approx(params.zoom_amount)
    pan = draw_motions([request("p", mode=MotionMode.MANUAL, manual_type=MotionType.PAN_UP)], 1, intensity)[
        "p"
    ]
    req = request("p")
    window_height = base_of(req)[1] / pan.start.scale
    assert abs(pan.end.centre_y - pan.start.centre_y) / window_height == pytest.approx(
        params.pan_amount, rel=1e-6
    )
    assert pan.end.centre_y < pan.start.centre_y  # PAN_UP: the window moves up


def test_stronger_intensity_moves_more() -> None:
    amounts = []
    for intensity in (Intensity.SOFT, Intensity.MEDIUM, Intensity.STRONG):
        req = request("z", mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_IN)
        m = draw_motions([req], 1, intensity)["z"]
        amounts.append(m.end.scale / m.start.scale)
    assert amounts == sorted(amounts) and len(set(amounts)) == 3


def test_blurred_photos_zoom_by_the_blur_factor() -> None:
    fill = draw_motions(
        [request("a", 4000, 3000, mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_IN)],
        1,
        Intensity.MEDIUM,
    )["a"]
    blur = draw_motions(
        [request("b", 3000, 4000, mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_IN)],
        1,
        Intensity.MEDIUM,
    )["b"]
    assert (blur.end.scale - 1) == pytest.approx((fill.end.scale - 1) * BLUR_INTENSITY_FACTOR)


def test_tiny_photo_stays_still() -> None:
    # 320x240 covers 1/6 of a 1920 px wide video: below 50 % -> no motion, even if requested.
    for mode, manual in ((MotionMode.AUTO, None), (MotionMode.MANUAL, MotionType.ZOOM_IN)):
        m = draw_motions([request("t", 320, 240, mode=mode, manual_type=manual)], 1, Intensity.STRONG)["t"]
        assert m.type is MotionType.NONE
        assert m.start == m.end and m.start.scale == 1.0


@pytest.mark.parametrize(
    ("width", "height"), [(1000, 750), (1200, 900), (1600, 1200), (2200, 1650), (8000, 6000)]
)
@pytest.mark.parametrize("output_format", list(OutputFormat))
def test_zoom_never_upscales_beyond_the_limit(width: int, height: int, output_format: OutputFormat) -> None:
    out_width = output_format.size[0]
    rng = np.random.default_rng(width)
    for i in range(200):
        req = request(f"u{i}", width, height, output_format=output_format, draw_count=int(rng.integers(100)))
        motion = draw_motions([req], int(rng.integers(1000)), Intensity.STRONG)[req.photo_id]
        window_px = req.fit.canvas_width * base_of(req)[0]
        limit = max(1.0, MAX_UPSCALE * window_px / out_width)
        assert max(motion.start.scale, motion.end.scale) <= limit + EPS


def test_low_resolution_photo_can_still_pan_where_there_is_room() -> None:
    # 1200x900: at scale 1 the photo is already enlarged 1.6x, so no zoom; it can only pan vertically.
    req = request("l", 1200, 900, mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_IN)
    assert draw_motions([req], 1, Intensity.MEDIUM)["l"].type is MotionType.NONE
    req = request("l", 1200, 900, mode=MotionMode.MANUAL, manual_type=MotionType.PAN_DOWN)
    m = draw_motions([req], 1, Intensity.MEDIUM)["l"]
    assert m.type is MotionType.PAN_DOWN and m.start.scale == 1.0
    autos = draw_motions([request(f"a{i}", 1200, 900, draw_count=i) for i in range(30)], 1, Intensity.MEDIUM)
    assert {m.type for m in autos.values()} <= {MotionType.PAN_UP, MotionType.PAN_DOWN, MotionType.NONE}


def test_very_short_durations_are_safe() -> None:
    for duration in (0.0, 0.1, 0.5):
        req = request("d", duration=duration)
        m = draw_motions([req], 1, Intensity.STRONG)["d"]
        assert m.type is not None


def test_forced_black_background_only_zooms() -> None:
    reqs = [request(f"k{i}", 4000, 3000, fit=FitMode.BLACK) for i in range(20)]
    motions = draw_motions(reqs, 1, Intensity.MEDIUM)
    assert {m.type for m in motions.values()} <= {MotionType.ZOOM_IN, MotionType.ZOOM_OUT}


@pytest.mark.parametrize("intensity", list(Intensity))
def test_presets_move_6_to_12_percent_per_photo(intensity: Intensity) -> None:
    amounts = INTENSITY_PRESETS[intensity]
    assert 0.06 <= amounts.zoom <= 0.12 and 0.06 <= amounts.pan <= 0.12
    for duration in (1.5, 2.0, 3.0, 4.0):  # visible time of 1-3 s photos with 0.5-1.5 s fades
        req = request("z", duration=duration, mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_IN)
        m = draw_motions([req], 1, intensity)["z"]
        assert m.end.scale / m.start.scale - 1 == pytest.approx(amounts.zoom)


@pytest.mark.parametrize(("zoom", "pan"), [(0.03, 0.15), (0.20, 0.05), (0.10, 0.10)])
def test_custom_amounts_are_applied(zoom: float, pan: float) -> None:
    amounts = MotionAmounts(zoom, pan)
    z = draw_motions([request("z", mode=MotionMode.MANUAL, manual_type=MotionType.ZOOM_OUT)], 1, amounts)["z"]
    assert z.start.scale / z.end.scale - 1 == pytest.approx(zoom)
    p = draw_motions([request("p", mode=MotionMode.MANUAL, manual_type=MotionType.PAN_DOWN)], 1, amounts)["p"]
    window_height = base_of(request("p"))[1] / p.start.scale
    assert (p.end.centre_y - p.start.centre_y) / window_height == pytest.approx(pan, rel=1e-6)


def test_zero_amounts_mean_still_photos() -> None:
    motions = draw_motions([request(f"s{i}") for i in range(10)], 1, MotionAmounts(0.0, 0.0))
    assert {m.type for m in motions.values()} == {MotionType.NONE}
