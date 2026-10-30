"""M08 · Black slides in the timeline: their own slot, the usual crossfades with the photo next to them."""

from __future__ import annotations

from dataclasses import replace

import pytest

from passimaker.model import BLACK_END_ID, BLACK_START_ID, BlackSlide, BlackSlidePosition, Project
from passimaker.timeline import compute_timeline, query
from tests.unit.timeline.helpers import make_project, make_song


def project_with_blacks(start_s: float = 2.0, end_s: float = 3.0) -> Project:
    base = make_project((2.0, 2.0))
    slides = (
        BlackSlide(BlackSlidePosition.START, start_s),
        *base.slides,
        BlackSlide(BlackSlidePosition.END, end_s),
    )
    return replace(base, slides=slides)


def test_black_slides_take_their_own_time_at_the_start_and_the_end() -> None:
    timeline = compute_timeline(project_with_blacks())
    assert timeline.total_duration_s == pytest.approx(9.0)
    assert [s.photo_id for s in timeline.slots] == [BLACK_START_ID, "p0", "p1", BLACK_END_ID]
    assert [s.black for s in timeline.slots] == [True, False, False, True]
    assert [s.index for s in timeline.slots] == [0, 1, 2, 3]
    first, photo, _, last = timeline.slots
    assert (first.slot_start, first.slot_end) == (0.0, 2.0)
    assert (photo.slot_start, photo.slot_end) == (2.0, 4.0)
    assert (last.slot_start, last.slot_end) == pytest.approx((6.0, 9.0))


def test_the_photo_next_to_a_black_slide_crossfades_with_it() -> None:
    timeline = compute_timeline(project_with_blacks())
    first, photo, _, last = timeline.slots
    # Crossfade of 1 s centred on the boundary, as between two photos.
    assert photo.fade_in is not None and (photo.fade_in.start, photo.fade_in.end) == (1.5, 2.5)
    assert first.fade_out == photo.fade_in
    assert last.fade_in is not None and (last.fade_in.start, last.fade_in.end) == pytest.approx((5.5, 6.5))
    middle = query(timeline, 2.0)
    assert [(layer.photo_id, layer.black) for layer in middle.layers] == [
        (BLACK_START_ID, True),
        ("p0", False),
    ]
    assert sum(layer.opacity for layer in middle.layers) == pytest.approx(1.0)
    assert [layer.black for layer in query(timeline, 0.5).layers] == [True]


def test_a_short_black_slide_shortens_the_crossfade_like_a_photo() -> None:
    timeline = compute_timeline(project_with_blacks(start_s=0.4))
    photo = timeline.slots[1]
    assert photo.fade_in is not None
    assert photo.fade_in.end - photo.fade_in.start == pytest.approx(0.2)


def test_the_black_fades_of_the_project_stay_at_the_ends_of_the_show() -> None:
    timeline = compute_timeline(project_with_blacks())
    assert timeline.fade_from_black is not None and timeline.fade_from_black.start == 0.0
    assert timeline.fade_to_black is not None and timeline.fade_to_black.end == pytest.approx(9.0)


def test_the_music_starts_with_the_black_slide() -> None:
    base = project_with_blacks()
    project = replace(base, music=replace(base.music, songs=(make_song(0, 30.0),)))
    plan = compute_timeline(project).audio_plan
    assert plan.segments[0].video_start == 0.0
