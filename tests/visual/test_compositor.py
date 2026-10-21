"""B6 · Compositor behaviour: real images, resolution choice, caches, threads and errors."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from passimaker.common import RGBImage
from passimaker.images import CachedImageSource, ImageDecodeError
from passimaker.importer import import_paths
from passimaker.model.types import MotionType, OutputFormat, Photo
from passimaker.render import Compositor
from passimaker.render.params import PLACEHOLDER_COLOR
from passimaker.thumbs import INTERMEDIATE_SIZE
from passimaker.timeline import compute_timeline
from tests.visual.helpers import (
    MemoryImageSource,
    build_project,
    compositor_for,
    frame_times,
    magenta_count,
    photo,
    synthetic_images,
)

REAL_PHOTOS = (
    "ratio_4x3.jpg",
    "ratio_9x16.jpg",
    "pano_3x1.jpg",
    "tiny_320x240.jpg",
    "huge_8000x6000.jpg",
    "cmyk.jpg",
    "alpha.png",
    "photo.heic",
    "orient_6.jpg",
    "orient_3.jpg",
)


def _real_photos(fixture_files: dict[str, Path]) -> list[Photo]:
    result = import_paths([fixture_files[name] for name in REAL_PHOTOS])
    assert not result.failures
    by_path = {c.path: c for c in result.candidates}
    candidates = [by_path[fixture_files[name]] for name in REAL_PHOTOS]
    return [
        Photo(f"r{i}", c.path, None, c.width, c.height, exif_orientation=c.exif_orientation)
        for i, c in enumerate(candidates)
    ]


@pytest.mark.parametrize("output_format", list(OutputFormat))
def test_real_photos_through_the_real_decoder(
    fixture_files: dict[str, Path], output_format: OutputFormat
) -> None:
    project = build_project(_real_photos(fixture_files), output_format)
    source = CachedImageSource(workers=1)
    try:
        compositor, timeline = compositor_for(project, source)
        width, height = (640, 360) if output_format is OutputFormat.HORIZONTAL else (360, 640)
        for t in frame_times(timeline, step=4):
            frame = compositor.frame_at(t, width, height, sentinel=True)
            assert magenta_count(frame) == 0, t
        middle = [(s.slot_start + s.slot_end) / 2 for s in timeline.slots]
        for t in middle:  # every photo was decoded (no grey placeholder)
            frame = compositor.frame_at(t, width, height)
            assert not (frame == np.array(PLACEHOLDER_COLOR, dtype=np.uint8)).all(axis=-1).mean() > 0.5
    finally:
        source.close()


def test_a_photo_that_cannot_be_decoded_is_drawn_grey(caplog: pytest.LogCaptureFixture) -> None:
    project = build_project([photo("ok", 4000, 3000), photo("missing", 4000, 3000), photo("ok2", 4000, 3000)])

    class Failing(MemoryImageSource):
        def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
            if photo.id == "missing":
                raise ImageDecodeError("images.not_found", str(photo.path))
            return super().get_image(photo, min_long_side)

    source = Failing(synthetic_images(project).images)
    compositor, timeline = compositor_for(project, source)
    slot = timeline.slots[1]
    with caplog.at_level(logging.WARNING, logger="passimaker.render"):
        frame = compositor.frame_at((slot.slot_start + slot.slot_end) / 2, 320, 180, sentinel=True)
    assert (frame == np.array(PLACEHOLDER_COLOR, dtype=np.uint8)).all()
    assert "missing" in caplog.text


def test_the_source_resolution_follows_the_output_size_and_the_zoom() -> None:
    photos = [photo("big", 8000, 6000), photo("small", 320, 240)]
    project = build_project(photos, motions={"big": MotionType.ZOOM_IN, "small": MotionType.ZOOM_IN})
    source = synthetic_images(project)
    compositor, _ = compositor_for(project, source)
    for t in (0.5, 2.5):
        compositor.frame_at(t, 1920, 1080)
        compositor.frame_at(t, 480, 270)
    requests: dict[str, list[int]] = {"big": [], "small": []}
    for photo_id, long_side in source.requests:
        requests[photo_id].append(long_side)
    big_1080, big_270 = requests["big"]
    scale = project.photos[0].motion.end.scale
    # A 4:3 photo in a 16:9 video: the scale-1 window is as wide as the photo, so the most
    # zoomed-in window (1 / scale of the width) must get 1920 image pixels.
    assert big_1080 == pytest.approx(1920 * scale, rel=0.01)
    assert big_270 == pytest.approx(big_1080 / 4, rel=0.01)
    assert requests["small"] == [320, 320]  # never more than the original
    assert len(source.requests) == 4  # one canvas per photo and size


def test_the_intermediate_image_serves_small_sizes() -> None:
    project = build_project([photo("p", 8000, 6000), photo("q", 8000, 6000)])
    source = synthetic_images(project)
    disk = synthetic_images(project)  # stands for the thumbnail service's disk cache
    served: list[str] = []

    def intermediate(p: Photo) -> RGBImage:
        served.append(p.id)
        if p.id == "q":
            raise ImageDecodeError("images.corrupt", "")
        return disk.get_image(p, INTERMEDIATE_SIZE)

    timeline = compute_timeline(project)
    compositor = Compositor(project, timeline, source, intermediate)
    compositor.frame_at(1.0, 960, 540)
    assert served == ["p"] and source.requests == []
    compositor.frame_at(3.0, 960, 540)  # q fails: falls back to the image source
    assert served == ["p", "q"] and [r[0] for r in source.requests] == ["q"]
    compositor.frame_at(1.0, 1920, 1080)  # too big for the intermediate
    assert served == ["p", "q"] and [r[0] for r in source.requests] == ["q", "p"]


def test_next_photos_are_prefetched_once() -> None:
    project = build_project([photo(f"p{i}", 4000, 3000) for i in range(5)])
    source = synthetic_images(project)
    compositor, _ = compositor_for(project, source)
    for t in (0.1, 0.2, 0.3):
        compositor.frame_at(t, 480, 270)
    assert [p for p, _ in source.prefetched] == ["p1", "p2"]
    compositor.frame_at(2.1, 480, 270)
    assert [p for p, _ in source.prefetched] == ["p1", "p2", "p3"]


def test_invalidate_drops_cached_canvases() -> None:
    project = build_project([photo("a", 4000, 3000), photo("b", 4000, 3000)])
    source = synthetic_images(project)
    compositor, _ = compositor_for(project, source)
    compositor.frame_at(1.0, 320, 180)
    compositor.frame_at(1.0, 320, 180)
    assert [r[0] for r in source.requests] == ["a"]
    compositor.invalidate(frozenset({"b"}))
    compositor.frame_at(1.0, 320, 180)
    assert [r[0] for r in source.requests] == ["a"]
    compositor.invalidate(frozenset({"a"}))
    compositor.frame_at(1.0, 320, 180)
    compositor.invalidate()
    compositor.frame_at(1.0, 320, 180)
    assert [r[0] for r in source.requests] == ["a", "a", "a"]


def test_concurrent_calls_give_the_same_frames() -> None:
    project = build_project(
        [photo(f"p{i}", w, h) for i, (w, h) in enumerate([(4000, 3000), (3000, 4000)] * 3)]
    )
    times = [t for t in frame_times(compute_timeline(project), step=3)]
    sequential, _ = compositor_for(project)
    expected = [sequential.frame_at(t, 320, 180) for t in times]
    shared, _ = compositor_for(project)
    with ThreadPoolExecutor(max_workers=4) as pool:
        frames = list(pool.map(lambda t: shared.frame_at(t, 320, 180), times))
    assert all(np.array_equal(a, b) for a, b in zip(expected, frames, strict=True))


def test_frames_belong_to_the_caller() -> None:
    project = build_project([photo("a", 4000, 3000), photo("b", 4000, 3000), photo("c", 4000, 3000)])
    compositor, _ = compositor_for(project)
    first = compositor.frame_at(3.0, 320, 180)
    assert first.flags.writeable and first.shape == (180, 320, 3) and first.dtype == np.uint8
    first[:] = 0
    assert compositor.frame_at(3.0, 320, 180).any()


def test_with_motion_off_photos_stay_still() -> None:
    project = build_project([photo(f"p{i}", 4000, 3000) for i in range(3)], motion_enabled=False)
    assert any(p.motion.type is not MotionType.NONE for p in project.photos)  # stored, but not used
    compositor, timeline = compositor_for(project)
    slot = timeline.slots[1]
    still = [compositor.frame_at(t, 320, 180) for t in (slot.fade_in.end + 0.01, slot.fade_out.start - 0.01)]  # type: ignore[union-attr]
    assert np.array_equal(still[0], still[1])


@pytest.mark.parametrize("size", [(1, 1), (7, 3), (33, 100)])
def test_any_size(size: tuple[int, int]) -> None:
    project = build_project([photo("a", 4000, 3000), photo("b", 1000, 3000)])
    compositor, _ = compositor_for(project)
    assert compositor.frame_at(1.9, *size, sentinel=True).shape == (size[1], size[0], 3)


def test_invalid_size_is_rejected() -> None:
    compositor, _ = compositor_for(build_project([photo("a", 4000, 3000)]))
    with pytest.raises(ValueError):
        compositor.frame_at(0.5, 0, 100)


def test_photos_of_a_project_edited_by_hand_keep_working() -> None:
    """A stored motion drawn for another fit is replaced by the whole canvas (no borders)."""
    project = build_project([photo("v", 3000, 4000)], OutputFormat.HORIZONTAL)
    moved = replace(project.photos[0], width=4000, height=3000)  # now FILL, motion was for BLUR
    project = replace(project, photos=(moved,))
    compositor, timeline = compositor_for(project, MemoryImageSource(synthetic_images(project).images))
    for t in frame_times(timeline, step=6):
        assert magenta_count(compositor.frame_at(t, 320, 180, sentinel=True)) == 0


def test_a_canvas_built_while_invalidating_is_not_kept() -> None:
    project = build_project([photo("a", 4000, 3000), photo("b", 4000, 3000)])
    images = synthetic_images(project).images

    class InvalidatesWhileDecoding(MemoryImageSource):
        def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
            image = super().get_image(photo, min_long_side)
            if len(self.requests) == 1:
                compositor.invalidate()  # e.g. the user rotated the photo meanwhile
            return image

    source = InvalidatesWhileDecoding(images)
    compositor, _ = compositor_for(project, source)
    compositor.frame_at(1.0, 320, 180)
    compositor.frame_at(1.0, 320, 180)
    assert [r[0] for r in source.requests] == ["a", "a"]
