"""M6 · Fit and motion generation (block B3).

Public API: resolve_fit, draw_motions, rebuild_motions, window_at, window_rect and the
parameters in passi.motion.params (the only place where motion amounts are tuned).
"""

from passi.motion.draw import MotionRequest, draw_motions, motion_speeds, option_of, rebuild_motions
from passi.motion.geometry import (
    FitDecision,
    base_window,
    is_inside,
    output_aspect,
    resolve_fit,
    window_at,
    window_rect,
)
from passi.motion.params import (
    BASE_PROBABILITIES,
    BLUR_INTENSITY_FACTOR,
    FILL_RATIO_RANGE,
    INTENSITY_PRESETS,
    MAX_UPSCALE,
    IntensityParams,
    MotionAmounts,
    intensity_params,
)

__all__ = [
    "BASE_PROBABILITIES",
    "BLUR_INTENSITY_FACTOR",
    "FILL_RATIO_RANGE",
    "INTENSITY_PRESETS",
    "MAX_UPSCALE",
    "FitDecision",
    "IntensityParams",
    "MotionAmounts",
    "MotionRequest",
    "base_window",
    "draw_motions",
    "intensity_params",
    "is_inside",
    "motion_speeds",
    "option_of",
    "output_aspect",
    "rebuild_motions",
    "resolve_fit",
    "window_at",
    "window_rect",
]
