"""B6 · Smooth motion: no jumps between consecutive frames, and no stops during the fades.

The motion between two frames is measured on the images themselves (the affine transform that
aligns them, so zooms count too) as the mean displacement of the four corners, in pixels.
The neighbouring photos are plain grey, so the mix can be undone and the photo's motion followed
through its crossfades.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from passimaker.model.types import FitMode, MotionType, OutputFormat
from passimaker.timeline import query
from tests.visual.helpers import (
    MemoryImageSource,
    build_project,
    compositor_for,
    frame_times,
    photo,
    solid,
    synthetic_images,
)

WIDTH, HEIGHT = 960, 540
GREY = (128, 128, 128)
MIN_WEIGHT = 0.25
"""Frames where the moving photo is fainter than this are too noisy to measure."""
MEASURE_SIZE = (480, 270)


def _grey(frame: NDArray[np.uint8]) -> NDArray[np.float32]:
    return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32)


def _displacements(frames: list[NDArray[np.float32]]) -> list[float]:
    """Mean corner displacement (px) of the affine transform between consecutive frames.

    Measured with OpenCV's ECC alignment on half-size copies (an affine transform also captures
    zoom). Each estimate starts from the previous one, since the motion is nearly constant.
    """
    small = [cv2.resize(f, MEASURE_SIZE, interpolation=cv2.INTER_AREA) for f in frames]
    width, height = MEASURE_SIZE
    corners = np.array([[0, 0, 1], [width, 0, 1], [0, height, 1], [width, height, 1]], dtype=np.float64).T
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 1e-4)
    warp = np.eye(2, 3, dtype=np.float32)
    result: list[float] = []
    for before, after in itertools.pairwise(small):
        _, warp = cv2.findTransformECC(before, after, warp.copy(), cv2.MOTION_AFFINE, criteria, None, 3)
        moved = warp.astype(np.float64) @ corners
        result.append(float(np.linalg.norm(moved - corners[:2], axis=0).mean()))
    return result


def _frames(
    motion: MotionType, size: tuple[int, int], output_format: OutputFormat, fit: FitMode = FitMode.AUTO
) -> list[NDArray[np.float32]]:
    """The middle photo over its whole visible span (fades included), unmixed, in grey levels."""
    # Two grey photos after it, so that its fade-out ends before the fade to black starts.
    photos = [photo("before", 1600, 1200), photo("moving", *size), photo("after", 1600, 1200)]
    photos.append(photo("last", 1600, 1200))
    project = build_project(photos, output_format, motions={"moving": motion}, fits={"moving": fit})
    assert project.photos[1].motion.type is motion
    images = synthetic_images(project).images | {
        "before": solid(1600, 1200, GREY),
        "after": solid(1600, 1200, GREY),
        "last": solid(1600, 1200, GREY),
    }
    compositor, timeline = compositor_for(project, MemoryImageSource(images))
    slot = timeline.slots[1]
    width, height = (WIDTH, HEIGHT) if output_format is OutputFormat.HORIZONTAL else (HEIGHT, WIDTH)
    frames: list[NDArray[np.float32]] = []
    for t in frame_times(timeline):
        weight = next(
            (layer.opacity for layer in query(timeline, t).layers if layer.photo_id == "moving"), 0.0
        )
        if weight < MIN_WEIGHT or not slot.visible_start < t < slot.visible_end:
            continue
        # Undo the mix with the grey neighbour (frame = w * photo + (1 - w) * grey).
        frame = (_grey(compositor.frame_at(t, width, height)) - (1 - weight) * GREY[0]) / weight
        frames.append(np.ascontiguousarray(frame.T) if output_format is OutputFormat.VERTICAL else frame)
    return frames


@pytest.mark.lent
@pytest.mark.parametrize(
    ("motion", "size", "output_format", "fit"),
    [
        (MotionType.ZOOM_IN, (4000, 3000), OutputFormat.HORIZONTAL, FitMode.AUTO),
        (MotionType.ZOOM_OUT, (4000, 3000), OutputFormat.HORIZONTAL, FitMode.AUTO),
        (MotionType.PAN_LEFT, (6000, 2000), OutputFormat.HORIZONTAL, FitMode.FILL),  # panorama
        (MotionType.PAN_RIGHT, (4000, 3000), OutputFormat.HORIZONTAL, FitMode.AUTO),
        (MotionType.PAN_UP, (4000, 3000), OutputFormat.HORIZONTAL, FitMode.AUTO),
        (MotionType.PAN_DOWN, (3000, 4000), OutputFormat.VERTICAL, FitMode.AUTO),
        (MotionType.COMBINED, (3000, 2000), OutputFormat.HORIZONTAL, FitMode.AUTO),
        (MotionType.ZOOM_IN, (3000, 4000), OutputFormat.HORIZONTAL, FitMode.AUTO),  # blurred background
    ],
)
def test_motion_has_no_jumps_and_does_not_stop_during_the_fades(
    motion: MotionType, size: tuple[int, int], output_format: OutputFormat, fit: FitMode
) -> None:
    profile = _displacements(_frames(motion, size, output_format, fit))
    median = float(np.median(profile))
    assert len(profile) >= 70  # most of the 3 s at 30 fps, well into both crossfades
    assert median > 0.2
    assert max(profile) <= 2 * median, [round(d, 3) for d in profile]
    assert min(profile) >= median / 2, [round(d, 3) for d in profile]  # it never stops


def test_a_static_photo_does_not_move() -> None:
    profile = _displacements(_frames(MotionType.NONE, (4000, 3000), OutputFormat.HORIZONTAL))
    assert max(profile) < 0.05


def test_the_measure_detects_jumps_and_stops() -> None:
    """Positive control: dropping frames makes a jump, repeating one makes a stop."""
    frames = _frames(MotionType.PAN_RIGHT, (4000, 3000), OutputFormat.HORIZONTAL)
    middle = len(frames) // 2
    jump = _displacements([*frames[:middle], *frames[middle + 2 :]])
    stop = _displacements([*frames[:middle], frames[middle - 1], *frames[middle:]])
    assert max(jump) > 2 * float(np.median(jump))
    assert min(stop) < float(np.median(stop)) / 2
