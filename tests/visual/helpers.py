"""Synthetic projects and image sources for the compositor tests (block B6).

Projects are built through the real controller (B1), so fits and motions come from B3 and the
timeline from B2, exactly as in the program.
"""

from __future__ import annotations

import functools
import zlib
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from passimaker.common import RGBImage
from passimaker.model.commands import AddPhotos, SetPhotoFit, SetPhotoMotion, SetProjectSettings
from passimaker.model.controller import ProjectController
from passimaker.model.types import FitMode, Intensity, MotionType, OutputFormat, Photo, Project
from passimaker.render import Compositor
from passimaker.timeline import Timeline, compute_timeline
from tests.fixtures.generate import MAX_MAGENTA_EXCESS, synthetic_rgb

ARTEFACTS = Path(__file__).resolve().parents[1] / "_artefactes" / "render"
QUARTER_ABOVE = 1200

# (width, height) of every proportion the program must handle.
SIZES: tuple[tuple[int, int], ...] = (
    (4000, 3000),  # 4:3
    (3000, 2000),  # 3:2
    (1920, 1080),  # 16:9
    (1080, 1920),  # 9:16
    (3000, 4000),  # 3:4
    (2000, 2000),  # 1:1
    (6000, 2000),  # 3:1 panorama
    (8000, 2000),  # 4:1 panorama
    (2000, 3000),  # 2:3
    (320, 240),  # tiny (static motion)
    (8000, 6000),  # 48 MP
    (900, 1200),  # small vertical
)

ALL_MOTIONS = (
    MotionType.ZOOM_IN,
    MotionType.ZOOM_OUT,
    MotionType.PAN_LEFT,
    MotionType.PAN_RIGHT,
    MotionType.PAN_UP,
    MotionType.PAN_DOWN,
    MotionType.COMBINED,
    MotionType.NONE,
)


def photo(photo_id: str, width: int, height: int, duration_s: float | None = None) -> Photo:
    return Photo(photo_id, Path(f"{photo_id}.jpg"), None, width, height, duration_s=duration_s)


def build_project(
    photos: Sequence[Photo],
    output_format: OutputFormat = OutputFormat.HORIZONTAL,
    *,
    seed: int = 7,
    motions: dict[str, MotionType] | None = None,
    fits: dict[str, FitMode] | None = None,
    intensity: Intensity | None = None,
    crossfade_s: float | None = None,
    motion_enabled: bool = True,
) -> Project:
    controller = ProjectController(Project(output_format=output_format, seed=seed))
    controller.execute(
        SetProjectSettings(intensity=intensity, crossfade_s=crossfade_s, motion_enabled=motion_enabled)
    )
    controller.execute(AddPhotos(tuple(photos)))
    for photo_id, fit in (fits or {}).items():
        controller.execute(SetPhotoFit(frozenset({photo_id}), fit))
    for photo_id, motion in (motions or {}).items():
        controller.execute(SetPhotoMotion(frozenset({photo_id}), motion))
    return controller.project


def synthetic_projects() -> dict[str, Project]:
    """Three projects with every proportion, every motion, both formats and both fits."""
    photos = [photo(f"p{i:02d}", w, h) for i, (w, h) in enumerate(SIZES)]
    manual = {p.id: ALL_MOTIONS[i % len(ALL_MOTIONS)] for i, p in enumerate(photos)}
    extra = [photo("x_fill_vertical", 3000, 4000), photo("x_black_pano", 6000, 2000)]
    fits = {"x_fill_vertical": FitMode.FILL, "x_black_pano": FitMode.BLACK}
    return {
        "horitzontal_auto": build_project([*photos, *extra], fits=fits),
        "vertical_manual": build_project(
            [*photos, *extra], OutputFormat.VERTICAL, motions=manual, fits=fits, seed=11
        ),
        "horitzontal_marcada": build_project(
            [photo(p.id, p.width, p.height, duration_s=(1.0, 3.0, 1.6)[i % 3]) for i, p in enumerate(photos)],
            motions={k: v for k, v in manual.items() if int(k[1:]) % 2},
            intensity=Intensity.STRONG,
            crossfade_s=1.5,
            seed=3,
        ),
    }


class MemoryImageSource:
    """ImageSource over fixed arrays (generated once per photo at its full size, capped)."""

    def __init__(self, images: dict[str, RGBImage]) -> None:
        self.images = images
        self.requests: list[tuple[str, int]] = []
        self.prefetched: list[tuple[str, int]] = []

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        self.requests.append((photo.id, min_long_side))
        image = self.images[photo.id]
        long_side = max(image.shape[:2])
        if long_side > 2 * min_long_side:
            scale = min_long_side / long_side
            size = (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale)))
            image = np.asarray(cv2.resize(image, size, interpolation=cv2.INTER_AREA), dtype=np.uint8)
            image.setflags(write=False)
        return image

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        self.prefetched.extend((p.id, min_long_side) for p in photos)


def synthetic_images(project: Project, max_long_side: int = 2400) -> MemoryImageSource:
    """Textured images with each photo's proportion (big photos are stored smaller: faster)."""
    return MemoryImageSource(
        {p.id: _synthetic(p.id, p.width, p.height, max_long_side) for p in project.photos}
    )


@functools.cache
def _synthetic(photo_id: str, width: int, height: int, max_long_side: int) -> RGBImage:
    """Big images are generated at a quarter of the size and enlarged (linear: no overshoot
    towards magenta); small ones at their own size, so that they keep their detail."""
    scale = min(1.0, max_long_side / max(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    seed = zlib.crc32(photo_id.encode("utf-8"))
    if max(size) <= QUARTER_ABOVE:
        image = synthetic_rgb(*size, seed)
    else:
        small = synthetic_rgb(max(1, size[0] // 4), max(1, size[1] // 4), seed)
        image = np.asarray(cv2.resize(small, size, interpolation=cv2.INTER_LINEAR), dtype=np.uint8)
    image.setflags(write=False)
    return image


def solid(width: int, height: int, colour: tuple[int, int, int]) -> RGBImage:
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = colour
    image.setflags(write=False)
    return image


def compositor_for(project: Project, source: object | None = None) -> tuple[Compositor, Timeline]:
    timeline = compute_timeline(project)
    images = source if source is not None else synthetic_images(project)
    return Compositor(project, timeline, images), timeline  # type: ignore[arg-type]


def frame_times(timeline: Timeline, step: int = 1) -> list[float]:
    """Export times: frame n is shown at n / fps."""
    return [n / timeline.fps for n in range(0, timeline.total_frames, step)]


def magenta_count(frame: NDArray[np.uint8]) -> int:
    """Pixels that look like the sentinel colour (photo content never does, see the fixtures)."""
    signed = frame.astype(np.int16)
    excess = np.minimum(signed[..., 0] - signed[..., 1], signed[..., 2] - signed[..., 1])
    return int(np.count_nonzero(excess > MAX_MAGENTA_EXCESS))


def luminance(frame: NDArray[np.uint8]) -> float:
    return float(frame.astype(np.float64).mean())


def psnr(a: NDArray[np.uint8], b: NDArray[np.uint8]) -> float:
    return float(cv2.PSNR(a, b))
