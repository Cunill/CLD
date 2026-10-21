"""Photo canvases at working resolution.

The canvas is the surface the motion windows are defined on (passimaker.motion.geometry): the
photo itself (FILL) or the photo centred on a surface with the output aspect (BLUR, BLACK). The
compositor prepares it once per photo and output size, at the smallest resolution that still
gives at least one image pixel per output pixel in the most zoomed-in window. Every frame is
then a single sub-pixel warp of this image, so slow pans and zooms do not jitter and large
photos are never shrunk by more than the motion's own zoom ratio (no shimmering).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from passimaker.common import RGBImage
from passimaker.model.types import OutputFormat, ResolvedFit
from passimaker.motion import FitDecision, base_window
from passimaker.render.params import (
    BLUR_DARKEN,
    BLUR_SIGMA_FRACTION,
    BLUR_WORK_LONG_SIDE,
    PLACEHOLDER_COLOR,
)


@dataclass(frozen=True, slots=True)
class Canvas:
    image: RGBImage
    """The whole canvas, read-only (shared between threads)."""
    scale_x: float
    """Image pixels per canvas pixel, horizontally."""
    scale_y: float

    @property
    def nbytes(self) -> int:
        return int(self.image.nbytes)


def canvas_scale(
    fit: FitDecision, output_format: OutputFormat, max_window_scale: float, width: int, height: int
) -> float:
    """Image pixels per canvas pixel so that the most zoomed-in window gets >= 1 per output pixel."""
    base_x, base_y = base_window(fit.canvas_width, fit.canvas_height, output_format)
    return max(
        width * max_window_scale / (base_x * fit.canvas_width),
        height * max_window_scale / (base_y * fit.canvas_height),
    )


def requested_long_side(photo_width: int, photo_height: int, scale: float) -> int:
    """Long side to ask the image source for (never more than the original)."""
    long_side = max(photo_width, photo_height)
    return max(1, min(long_side, math.ceil(long_side * scale)))


def build_canvas(
    image: RGBImage, fit: FitDecision, photo_width: int, photo_height: int, scale: float
) -> Canvas:
    """Canvas from a decoded photo (oriented, any size >= the target, or the original if smaller)."""
    photo = _fit_photo(image, photo_width, photo_height, scale)
    img_h, img_w = photo.shape[:2]
    if fit.fit is ResolvedFit.FILL:
        return _read_only(photo, img_w / fit.canvas_width, img_h / fit.canvas_height)
    canvas_w = max(img_w, round(fit.canvas_width * img_w / photo_width))
    canvas_h = max(img_h, round(fit.canvas_height * img_h / photo_height))
    if fit.fit is ResolvedFit.BLUR:
        canvas = blurred_background(photo, canvas_w, canvas_h)
    else:
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    x, y = round((canvas_w - img_w) / 2), round((canvas_h - img_h) / 2)
    canvas[y : y + img_h, x : x + img_w] = photo
    return _read_only(canvas, canvas_w / fit.canvas_width, canvas_h / fit.canvas_height)


def placeholder_canvas(fit: FitDecision) -> Canvas:
    """Plain canvas for a photo that cannot be decoded (it keeps the canvas geometry)."""
    long_side = max(fit.canvas_width, fit.canvas_height)
    width = max(1, round(16 * fit.canvas_width / long_side))
    height = max(1, round(16 * fit.canvas_height / long_side))
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = PLACEHOLDER_COLOR
    return _read_only(image, width / fit.canvas_width, height / fit.canvas_height)


def blurred_background(photo: RGBImage, width: int, height: int) -> RGBImage:
    """The photo scaled to cover width x height, strongly blurred and darkened (§1.6).

    Computed on a small copy: the result is so smooth that enlarging it adds no visible detail.
    """
    small_scale = BLUR_WORK_LONG_SIDE / max(width, height)
    small_w, small_h = max(1, round(width * small_scale)), max(1, round(height * small_scale))
    img_h, img_w = photo.shape[:2]
    cover = max(small_w / img_w, small_h / img_h)
    cover_w, cover_h = max(small_w, math.ceil(img_w * cover)), max(small_h, math.ceil(img_h * cover))
    covered = cv2.resize(photo, (cover_w, cover_h), interpolation=cv2.INTER_AREA)
    x0, y0 = (cover_w - small_w) // 2, (cover_h - small_h) // 2
    small = covered[y0 : y0 + small_h, x0 : x0 + small_w]
    sigma = max(1.0, max(small_w, small_h) * BLUR_SIGMA_FRACTION)
    blurred = cv2.GaussianBlur(small, (0, 0), sigmaX=sigma, borderType=cv2.BORDER_REFLECT)
    darkened = cv2.convertScaleAbs(blurred, alpha=1.0 - BLUR_DARKEN)
    return as_image(cv2.resize(darkened, (width, height), interpolation=cv2.INTER_LINEAR))


def _fit_photo(image: RGBImage, photo_width: int, photo_height: int, scale: float) -> RGBImage:
    """Shrinks the decoded image to the working size (area filter); never enlarges it."""
    target_w = max(1, round(photo_width * min(1.0, scale)))
    target_h = max(1, round(photo_height * min(1.0, scale)))
    img_h, img_w = image.shape[:2]
    if img_w <= target_w or img_h <= target_h:
        return image
    return as_image(cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA))


def as_image(result: Any) -> RGBImage:
    """Types an OpenCV result computed from uint8 images (OpenCV keeps the depth)."""
    return result


def _read_only(image: RGBImage, scale_x: float, scale_y: float) -> Canvas:
    image = np.ascontiguousarray(image)
    image.setflags(write=False)
    return Canvas(image, scale_x, scale_y)
