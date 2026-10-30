"""M08 · The compositor draws the black slides black, and mixes them with the next photo in a crossfade."""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise

import numpy as np

from passimaker.model import BlackSlide, BlackSlidePosition
from passimaker.model.types import Project
from tests.visual.helpers import (
    build_project,
    compositor_for,
    luminance,
    magenta_count,
    photo,
    synthetic_images,
)

W, H = 320, 180


def with_blacks(project: Project) -> Project:
    slides = (BlackSlide(BlackSlidePosition.START), *project.slides, BlackSlide(BlackSlidePosition.END))
    return replace(project, slides=slides, fade_from_black_s=0.0, fade_to_black_s=0.0)


def test_black_slides_are_black_frames_and_ask_for_no_image() -> None:
    plain = build_project([photo("a", 4000, 3000), photo("b", 3000, 4000)])
    project = with_blacks(plain)
    source = synthetic_images(project)
    compositor, timeline = compositor_for(project, source)
    for t in (0.0, 0.5, 1.4, timeline.total_duration_s - 1.4, timeline.total_duration_s):
        frame = compositor.frame_at(t, W, H)
        assert not frame.any(), t
    assert all(pid in {"a", "b"} for pid, _ in source.requests)
    # In sentinel mode a black slide is content, not "outside the image".
    assert magenta_count(compositor.frame_at(0.5, W, H, sentinel=True)) == 0


def test_the_crossfade_with_a_black_slide_is_a_fade_from_and_to_black() -> None:
    project = with_blacks(build_project([photo("a", 4000, 3000)]))
    compositor, timeline = compositor_for(project)
    photo_slot = timeline.slots[1]
    assert photo_slot.fade_in is not None and photo_slot.fade_out is not None
    start, end = photo_slot.fade_in.start, photo_slot.fade_in.end
    levels = [luminance(compositor.frame_at(start + (end - start) * k / 4, W, H)) for k in range(5)]
    assert levels[0] == 0.0
    assert all(a < b for a, b in pairwise(levels))
    full = luminance(compositor.frame_at(photo_slot.slot_start + 1.0, W, H))
    assert np.isclose(levels[2], full / 2, rtol=0.15)


def test_the_first_photo_is_prefetched_during_the_black_slide() -> None:
    project = with_blacks(build_project([photo("a", 4000, 3000), photo("b", 4000, 3000)]))
    source = synthetic_images(project)
    compositor, _ = compositor_for(project, source)
    compositor.frame_at(0.2, W, H)
    assert any(pid == "a" for pid, _ in source.prefetched)
