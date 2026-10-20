"""M6 · Fit and motion generation (block B3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from passi.model.types import (
    FitMode,
    Intensity,
    MotionMode,
    MotionType,
    OutputFormat,
    PhotoMotion,
    ResolvedFit,
    Window,
)

FILL_RATIO_RANGE = (0.70, 1.43)
"""Photo aspect / video aspect inside this range -> FILL, otherwise BLUR (§1.6)."""

BASE_PROBABILITIES: Mapping[MotionType, float] = {
    MotionType.ZOOM_IN: 0.30,
    MotionType.ZOOM_OUT: 0.25,
    MotionType.PAN_LEFT: 0.0625,
    MotionType.PAN_RIGHT: 0.0625,
    MotionType.PAN_UP: 0.0625,
    MotionType.PAN_DOWN: 0.0625,
    MotionType.COMBINED: 0.20,
}


@dataclass(frozen=True, slots=True)
class IntensityParams:
    zoom_amount: float
    """Scale change over a photo (0.12 = 12 %)."""
    pan_amount: float
    """Displacement as a fraction of the canvas side."""
    max_zoom_speed: float
    """Per second."""
    max_pan_speed: float


INTENSITY_PARAMS: Mapping[Intensity, IntensityParams] = {
    Intensity.SOFT: IntensityParams(0.06, 0.04, 0.020, 0.015),
    Intensity.MEDIUM: IntensityParams(0.12, 0.08, 0.035, 0.025),
    Intensity.STRONG: IntensityParams(0.20, 0.13, 0.050, 0.040),
}
BLUR_INTENSITY_FACTOR = 0.6
MAX_UPSCALE = 1.5


@dataclass(frozen=True, slots=True)
class FitDecision:
    fit: ResolvedFit
    canvas_width: int
    canvas_height: int
    """Canvas size in source pixels: the photo itself (FILL) or the composed canvas (BLUR/BLACK)."""


@dataclass(frozen=True, slots=True)
class MotionRequest:
    photo_id: str
    width: int
    height: int
    visible_duration_s: float
    fit: FitDecision
    mode: MotionMode
    manual_type: MotionType | None
    """Fixed type for MANUAL mode."""
    draw_count: int


def resolve_fit(width: int, height: int, output_format: OutputFormat, preference: FitMode) -> FitDecision:
    raise NotImplementedError("B3")


def draw_motions(
    requests: Sequence[MotionRequest],
    seed: int,
    intensity: Intensity,
    which: frozenset[str] | None = None,
) -> dict[str, PhotoMotion]:
    """Draws motions applying the balance rules (§1.5). Photos not in `which` keep their
    current motion but are taken into account as neighbours. Deterministic for a given seed."""
    raise NotImplementedError("B3")


def window_at(motion: PhotoMotion, progress: float) -> Window:
    """Interpolated window for progress in [0, 1]; always inside the canvas."""
    raise NotImplementedError("B3")
