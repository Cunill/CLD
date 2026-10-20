"""Conversion between seconds and frame indices."""

from __future__ import annotations

import math

from passimaker.model import defaults

_FRAME_EPSILON = 1e-6
"""Tolerance in frames, so that t = n / fps always maps back to n despite float rounding."""


def frame_to_time(frame: int, fps: int = defaults.FPS) -> float:
    """Time in seconds at which frame `frame` is shown (computed directly, never accumulated)."""
    return frame / fps


def time_to_frame(t: float, fps: int = defaults.FPS) -> int:
    """Index of the frame on screen at time t (the last frame starting at or before t)."""
    return math.floor(t * fps + _FRAME_EPSILON)
