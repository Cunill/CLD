"""B6 · Crossfades and black fades."""

from __future__ import annotations

import numpy as np

from passimaker.model.types import MotionType, Project
from passimaker.timeline import query
from tests.visual.helpers import (
    MemoryImageSource,
    build_project,
    compositor_for,
    frame_times,
    luminance,
    photo,
    solid,
    synthetic_images,
)

RED = (220, 30, 20)
BLUE = (20, 40, 210)


def _red_blue() -> MemoryImageSource:
    blue = solid(1600, 1200, BLUE)
    return MemoryImageSource({"red": solid(1600, 1200, RED), "blue": blue, "blue2": blue})


def _red_blue_project() -> Project:
    """Red, blue, blue: the red-blue crossfade is clear of the fade to black."""
    return build_project([photo("red", 1600, 1200), photo("blue", 1600, 1200), photo("blue2", 1600, 1200)])


def test_halfway_through_a_crossfade_the_colour_is_the_average() -> None:
    compositor, timeline = compositor_for(_red_blue_project(), _red_blue())
    change = timeline.slots[1].slot_start
    visibles = query(timeline, change)
    assert [layer.photo_id for layer in visibles.layers] == ["red", "blue"]
    assert visibles.black_level == 0.0
    frame = compositor.frame_at(change, 480, 270).astype(np.float64)
    expected = (np.array(RED) + np.array(BLUE)) / 2
    assert np.abs(frame.reshape(-1, 3) - expected).max() <= 3


def test_the_crossfade_moves_steadily_from_one_photo_to_the_other() -> None:
    compositor, timeline = compositor_for(_red_blue_project(), _red_blue())
    fade = timeline.slots[1].fade_in
    assert fade is not None
    reds = [
        float(compositor.frame_at(t, 160, 90)[..., 0].mean())
        for t in frame_times(timeline)
        if fade.start <= t <= fade.end
    ]
    assert len(reds) >= 25
    steps = np.diff(reds)
    assert (steps < 0).all()
    assert steps.max() - steps.min() <= 2  # linear ramp, up to rounding
    assert abs(reds[0] - RED[0]) <= 7 and abs(reds[-1] - BLUE[0]) <= 7


def test_fades_from_and_to_black() -> None:
    photos = [photo(f"p{i}", 4000, 3000) for i in range(3)]
    project = build_project(photos, motions={p.id: MotionType.ZOOM_IN for p in photos})
    compositor, timeline = compositor_for(project, synthetic_images(project))
    fade_in, fade_out = timeline.fade_from_black, timeline.fade_to_black
    assert fade_in is not None and fade_out is not None
    assert luminance(compositor.frame_at(0.0, 480, 270)) == 0.0
    assert luminance(compositor.frame_at(timeline.total_duration_s, 480, 270)) == 0.0
    times = frame_times(timeline)
    rising = [luminance(compositor.frame_at(t, 480, 270)) for t in times if t <= fade_in.end]
    falling = [luminance(compositor.frame_at(t, 480, 270)) for t in times if t >= fade_out.start]
    assert all(b > a for a, b in zip(rising, rising[1:], strict=False))
    assert all(b < a for a, b in zip(falling, falling[1:], strict=False))
    # The last exported frame is shown 1/30 s before the end, so it is not quite black (see B06.md).
    assert falling[-1] < 0.03 * falling[0]


def test_without_photos_or_outside_the_show_the_frame_is_black() -> None:
    project = build_project([])
    compositor, _ = compositor_for(project, MemoryImageSource({}))
    assert luminance(compositor.frame_at(1.0, 64, 36)) == 0.0
    project = build_project([photo("red", 1600, 1200)])
    compositor, timeline = compositor_for(project, _red_blue())
    assert luminance(compositor.frame_at(-1.0, 64, 36)) == 0.0
    assert luminance(compositor.frame_at(timeline.total_duration_s + 1, 64, 36)) == 0.0
    assert luminance(compositor.frame_at(timeline.total_duration_s / 2, 64, 36)) > 50
