"""Fit decision and window geometry.

Coordinates: a window is described on the photo *canvas* (the photo itself for FILL, or the
photo centred on a canvas with the output aspect for BLUR/BLACK) with a normalised centre and a
scale. At scale 1 the window is the largest rectangle with the output aspect that fits in the
canvas; its normalised size is (base_x, base_y), and at scale s it is (base_x / s, base_y / s).

Interpolation (window_at) is linear for the centre and geometric for the scale. The edge
constraints (e.g. left = cx - base_x / (2 s) >= 0) are then concave functions of the progress,
so if both end windows are inside the canvas, every intermediate window is inside too.
"""

from __future__ import annotations

from dataclasses import dataclass

from passi.model.types import FitMode, OutputFormat, PhotoMotion, ResolvedFit, Window
from passi.motion.params import FILL_RATIO_RANGE

EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class FitDecision:
    fit: ResolvedFit
    canvas_width: int
    canvas_height: int
    """Canvas size in source pixels: the photo itself (FILL) or the composed canvas (BLUR/BLACK)."""


def output_aspect(output_format: OutputFormat) -> float:
    width, height = output_format.size
    return width / height


def resolve_fit(width: int, height: int, output_format: OutputFormat, preference: FitMode) -> FitDecision:
    """Applies the fit rule of §1.6 (AUTO) or the user's choice, and computes the canvas."""
    if width <= 0 or height <= 0:
        raise ValueError(f"mida de foto no vàlida: {width}x{height}")
    video_aspect = output_aspect(output_format)
    photo_aspect = width / height
    if preference is FitMode.AUTO:
        low, high = FILL_RATIO_RANGE
        fit = ResolvedFit.FILL if low <= photo_aspect / video_aspect <= high else ResolvedFit.BLUR
    else:
        fit = {
            FitMode.FILL: ResolvedFit.FILL,
            FitMode.BLUR: ResolvedFit.BLUR,
            FitMode.BLACK: ResolvedFit.BLACK,
        }[preference]
    if fit is ResolvedFit.FILL:
        return FitDecision(fit, width, height)
    if photo_aspect < video_aspect:
        return FitDecision(fit, max(width, round(height * video_aspect)), height)
    return FitDecision(fit, width, max(height, round(width / video_aspect)))


def base_window(canvas_width: int, canvas_height: int, output_format: OutputFormat) -> tuple[float, float]:
    """Normalised size (base_x, base_y) of the scale-1 window on the canvas."""
    video_aspect = output_aspect(output_format)
    canvas_aspect = canvas_width / canvas_height
    if canvas_aspect >= video_aspect:
        return video_aspect / canvas_aspect, 1.0
    return 1.0, canvas_aspect / video_aspect


def centre_range(size: float) -> tuple[float, float]:
    """Allowed centre interval for a window of normalised size `size` along one axis."""
    half = min(size, 1.0) / 2
    return half, 1.0 - half


def is_inside(window: Window, base: tuple[float, float], tolerance: float = EPSILON) -> bool:
    """True when the window lies inside the canvas (and is not larger than the scale-1 window)."""
    if window.scale < 1.0 - tolerance:
        return False
    width, height = base[0] / window.scale, base[1] / window.scale
    return (
        window.centre_x - width / 2 >= -tolerance
        and window.centre_x + width / 2 <= 1.0 + tolerance
        and window.centre_y - height / 2 >= -tolerance
        and window.centre_y + height / 2 <= 1.0 + tolerance
    )


def window_at(motion: PhotoMotion, progress: float) -> Window:
    """Interpolated window for progress in [0, 1] (clamped): linear centre, geometric scale."""
    p = min(1.0, max(0.0, progress))
    start, end = motion.start, motion.end
    return Window(
        start.centre_x + (end.centre_x - start.centre_x) * p,
        start.centre_y + (end.centre_y - start.centre_y) * p,
        start.scale * (end.scale / start.scale) ** p,
    )


def window_rect(
    window: Window, fit: FitDecision, output_format: OutputFormat
) -> tuple[float, float, float, float]:
    """Window as (left, top, right, bottom) in canvas pixels."""
    base_x, base_y = base_window(fit.canvas_width, fit.canvas_height, output_format)
    half_w = base_x / window.scale / 2 * fit.canvas_width
    half_h = base_y / window.scale / 2 * fit.canvas_height
    cx, cy = window.centre_x * fit.canvas_width, window.centre_y * fit.canvas_height
    return cx - half_w, cy - half_h, cx + half_w, cy + half_h
