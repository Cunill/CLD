"""Motion parameters (docs/ESPECIFICACIO.md §1.5 and §1.6).

This is the only place where motion amounts, speeds and probabilities live, so they can be
tuned after the visual review at milestone F1 without touching the algorithm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from passi.model.types import Intensity, MotionType

FILL_RATIO_RANGE = (0.70, 1.43)
"""Photo aspect / video aspect inside this range (inclusive) -> FILL, otherwise BLUR (§1.6)."""

BASE_PROBABILITIES: Mapping[MotionType, float] = {
    MotionType.ZOOM_IN: 0.30,
    MotionType.ZOOM_OUT: 0.25,
    MotionType.PAN_LEFT: 0.0625,
    MotionType.PAN_RIGHT: 0.0625,
    MotionType.PAN_UP: 0.0625,
    MotionType.PAN_DOWN: 0.0625,
    MotionType.COMBINED: 0.20,
}
"""Starting probabilities of the automatic draw. Pans share 25 %; the axis with more room
gets PREFERRED_PAN_AXIS_SHARE of it (rule 5)."""

PREFERRED_PAN_AXIS_SHARE = 0.75

RULE_COMPENSATION: Mapping[MotionType, float] = {
    MotionType.ZOOM_IN: 2.0 * 1.15,
    MotionType.ZOOM_OUT: 2.0,
    MotionType.PAN_LEFT: 0.8,
    MotionType.PAN_RIGHT: 0.8,
    MotionType.PAN_UP: 0.8,
    MotionType.PAN_DOWN: 0.8,
    MotionType.COMBINED: 0.9,
}
"""Internal weight multipliers. The balance rules (at most two zooms in a row...) penalise the
zoom family; these factors compensate so that the resulting distribution over a long show is
close to BASE_PROBABILITIES (measured in tests/unit/motion/test_rules.py)."""


@dataclass(frozen=True, slots=True)
class MotionAmounts:
    """Motion per photo, adjustable by the user (Project.zoom_amount / pan_amount)."""

    zoom: float
    """Scale change while the photo is visible (0.09 = 9 %)."""
    pan: float
    """Displacement while the photo is visible, as a fraction of the visible window side."""


INTENSITY_PRESETS: Mapping[Intensity, MotionAmounts] = {
    Intensity.SOFT: MotionAmounts(0.06, 0.06),
    Intensity.MEDIUM: MotionAmounts(0.09, 0.09),
    Intensity.STRONG: MotionAmounts(0.12, 0.12),
}
"""Decision 0005: every photo moves 6-12 % (soft-strong) during the time it is visible."""

FULL_MOTION_MIN_S = 1.0
"""Photos visible less than this do only part of their motion: the speed never exceeds the
amount per FULL_MOTION_MIN_S seconds."""


@dataclass(frozen=True, slots=True)
class IntensityParams:
    zoom_amount: float
    """Scale change over one photo (0.12 = the image ends 12 % larger or smaller)."""
    pan_amount: float
    """Displacement over one photo, as a fraction of the visible window side."""
    max_zoom_speed: float
    """Maximum scale change per second (fraction per second)."""
    max_pan_speed: float
    """Maximum displacement per second, as a fraction of the visible window side."""


BLUR_INTENSITY_FACTOR = 1.0
"""Zoom amount multiplier for photos fitted on a blurred (or black) background."""

COMBINED_ZOOM_FACTOR = 0.6
"""Combined motions zoom less and pan less than the pure motions, so the sum stays moderate."""
COMBINED_PAN_FACTOR = 0.7

MAX_UPSCALE = 1.5
"""Zoom never enlarges the source more than this (unless the photo is already smaller)."""
NO_MOTION_BELOW = 0.5
"""If the visible window at scale 1 covers less than this fraction of the output pixels, the
photo stays still (motion NONE)."""

MIN_ZOOM = 0.02
MIN_PAN = 0.02
"""Below these amounts a motion is not worth it and the type is considered not feasible."""

FOCAL_POINT = (0.5, 0.45)
"""Default target of zooms: slightly above the centre, where faces usually are."""
FOCAL_JITTER = (0.08, 0.05)
"""Random offset (+/-) applied to the focal point for variety."""

BALANCE_WINDOW = 6
MAX_ZOOM_IMBALANCE = 2
MAX_FAMILY_RUN = 2


def intensity_params(amounts: MotionAmounts | Intensity) -> IntensityParams:
    """Amounts and speed limits used by the draw, from user amounts or a preset."""
    if isinstance(amounts, Intensity):
        amounts = INTENSITY_PRESETS[amounts]
    return IntensityParams(
        zoom_amount=amounts.zoom,
        pan_amount=amounts.pan,
        max_zoom_speed=amounts.zoom / FULL_MOTION_MIN_S,
        max_pan_speed=amounts.pan / FULL_MOTION_MIN_S,
    )
