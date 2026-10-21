"""B6 · Blurred background: the photo is seen whole, over a smooth, darker copy of itself."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from passimaker.model.types import FitMode, MotionType, OutputFormat, ResolvedFit
from passimaker.motion import resolve_fit
from passimaker.render.params import BLUR_DARKEN
from tests.visual.helpers import build_project, compositor_for, photo, psnr, synthetic_images

CASES = [
    ((3000, 4000), OutputFormat.HORIZONTAL),  # vertical photo, horizontal video
    ((2000, 2000), OutputFormat.HORIZONTAL),  # square
    ((6000, 2000), OutputFormat.HORIZONTAL),  # 3:1 panorama
    ((4000, 3000), OutputFormat.VERTICAL),  # horizontal photo, vertical video
]


def _photo_box(
    size: tuple[int, int], output_format: OutputFormat, frame_size: tuple[int, int]
) -> tuple[float, ...]:
    """Where the whole photo should appear in a static frame: (left, top, right, bottom) in px."""
    fit = resolve_fit(*size, output_format, FitMode.AUTO)
    assert fit.fit is ResolvedFit.BLUR
    sx, sy = frame_size[0] / fit.canvas_width, frame_size[1] / fit.canvas_height
    left, top = (fit.canvas_width - size[0]) / 2, (fit.canvas_height - size[1]) / 2
    return left * sx, top * sy, (left + size[0]) * sx, (top + size[1]) * sy


def _static_frame(
    size: tuple[int, int], output_format: OutputFormat
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], tuple[int, int]]:
    """The middle of three photos, static, halfway through its slot (no fade at all)."""
    photos = [photo("a", 4000, 3000), photo("p", *size), photo("b", 4000, 3000)]
    project = build_project(photos, output_format, motions={"p": MotionType.NONE})
    source = synthetic_images(project)
    compositor, timeline = compositor_for(project, source)
    slot = timeline.slots[1]
    frame_size = (960, 540) if output_format is OutputFormat.HORIZONTAL else (540, 960)
    frame = compositor.frame_at((slot.slot_start + slot.slot_end) / 2, *frame_size)
    return frame, source.images["p"], frame_size


@pytest.mark.parametrize(("size", "output_format"), CASES)
def test_the_whole_photo_is_visible(size: tuple[int, int], output_format: OutputFormat) -> None:
    frame, image, frame_size = _static_frame(size, output_format)
    left, top, right, bottom = _photo_box(size, output_format, frame_size)
    x0, y0, x1, y1 = round(left), round(top), round(right), round(bottom)
    expected = np.asarray(cv2.resize(image, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA), dtype=np.uint8)
    # One pixel in from each side: the photo's outermost pixels blend with the background.
    inner = frame[y0 + 1 : y1 - 1, x0 + 1 : x1 - 1]
    assert psnr(inner, expected[1:-1, 1:-1]) > 30


@pytest.mark.parametrize(("size", "output_format"), CASES)
def test_the_background_is_smooth_and_darker(size: tuple[int, int], output_format: OutputFormat) -> None:
    frame, image, frame_size = _static_frame(size, output_format)
    left, top, right, bottom = _photo_box(size, output_format, frame_size)
    signed = frame.astype(np.int16)
    if right - left < frame_size[0] - 2:  # bands at the left and right
        bands = [signed[:, : int(left) - 2], signed[:, int(right) + 3 :]]
    else:  # bands at the top and bottom
        bands = [signed[: int(top) - 2], signed[int(bottom) + 3 :]]
    for band in bands:
        assert band.shape[0] > 10 and band.shape[1] > 10
        # No marked edges anywhere in the background, its outer border included.
        steps = max(int(np.abs(np.diff(band, axis=0)).max()), int(np.abs(np.diff(band, axis=1)).max()))
        assert steps <= 3
    # Darkened by 30 %: the blur keeps the average, so the bands are about 70 % of the photo's.
    ratio = float(np.concatenate([b.reshape(-1, 3) for b in bands]).mean()) / float(image.mean())
    assert abs(ratio - (1 - BLUR_DARKEN)) < 0.12
