"""Rendering constants of the compositor (fixed look, not user settings).

User-facing defaults and ranges live in passimaker.model.defaults and motion amounts in
passimaker.motion.params; these values only describe how a frame is drawn.
"""

from __future__ import annotations

SENTINEL_COLOR: tuple[int, int, int] = (255, 0, 255)
"""In sentinel mode every pixel outside the photo canvas is painted with this colour."""

BLUR_WORK_LONG_SIDE = 256
"""The blurred background is computed on a copy whose long side has this size, then enlarged."""
BLUR_SIGMA_FRACTION = 1 / 40
"""Gaussian sigma as a fraction of the canvas long side (the look approved at milestone F1)."""
BLUR_DARKEN = 0.30
"""The blurred background is darkened by this fraction (§1.6: 30 %)."""

PLACEHOLDER_COLOR: tuple[int, int, int] = (64, 64, 64)
"""Canvas colour for a photo that cannot be decoded (missing or damaged file)."""

CANVAS_CACHE_BYTES = 192 * 1024 * 1024
"""Memory budget of the prepared canvases (several output sizes and photos at once)."""

PREFETCH_AHEAD = 2
"""Photos after the one on screen whose images are requested in advance."""

EDGE_TOLERANCE_PX = 1e-3
"""Sentinel test tolerance: a pixel centre this close to the canvas edge still counts as inside."""
