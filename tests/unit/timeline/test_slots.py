"""B2 · Slots, crossfades and black fades (ESPECIFICACIO §1.3 and §1.4)."""

from __future__ import annotations

import itertools
import math

import pytest
from hypothesis import given

from passi.model.types import Project
from passi.timeline import compute_timeline
from tests.unit.timeline.helpers import make_project, projects


@given(projects(wide=True))
def test_total_is_the_sum_of_the_durations(project: Project) -> None:
    timeline = compute_timeline(project)
    expected = math.fsum(project.photo_duration(p) for p in project.photos)
    assert timeline.total_duration_s == pytest.approx(expected, rel=1e-12, abs=1e-12)
    assert timeline.total_frames == round(timeline.total_duration_s * 30)
    assert [s.photo_id for s in timeline.slots] == [p.id for p in project.photos]
    assert [s.index for s in timeline.slots] == list(range(len(project.photos)))


@given(projects(min_photos=1, wide=True))
def test_slots_are_contiguous_and_match_each_duration(project: Project) -> None:
    timeline = compute_timeline(project)
    slots = timeline.slots
    assert slots[0].slot_start == 0.0
    assert slots[-1].slot_end == timeline.total_duration_s
    for before, after in itertools.pairwise(slots):
        assert before.slot_end == after.slot_start
    for slot, photo in zip(slots, project.photos, strict=True):
        assert slot.slot_end - slot.slot_start == pytest.approx(project.photo_duration(photo), abs=1e-9)


@given(projects(min_photos=2, wide=True))
def test_crossfade_is_centred_and_never_exceeds_half_of_the_shorter_photo(project: Project) -> None:
    timeline = compute_timeline(project)
    for before, after in itertools.pairwise(timeline.slots):
        shorter = min(before.slot_end - before.slot_start, after.slot_end - after.slot_start)
        assert before.fade_out == after.fade_in
        fade = after.fade_in
        if fade is None:
            assert min(project.crossfade_s, shorter / 2) < 1e-9  # no length left once rounded
            continue
        length = fade.end - fade.start
        assert length <= shorter / 2 + 1e-12
        assert length == pytest.approx(min(project.crossfade_s, shorter / 2), abs=1e-12)
        assert (fade.start + fade.end) / 2 == pytest.approx(after.slot_start, abs=1e-9)
        assert before.visible_end == fade.end and after.visible_start == fade.start


@given(projects(min_photos=1, wide=True))
def test_every_photo_is_fully_visible_at_some_moment(project: Project) -> None:
    timeline = compute_timeline(project)
    for slot in timeline.slots:
        solo_start = slot.fade_in.end if slot.fade_in is not None else slot.visible_start
        solo_end = slot.fade_out.start if slot.fade_out is not None else slot.visible_end
        assert solo_end - solo_start >= (slot.slot_end - slot.slot_start) / 2 - 1e-9


def test_no_photos_gives_an_empty_timeline() -> None:
    timeline = compute_timeline(Project())
    assert timeline.slots == ()
    assert timeline.total_duration_s == 0.0
    assert timeline.total_frames == 0
    assert timeline.fade_from_black is None and timeline.fade_to_black is None
    assert timeline.audio_plan.segments == () and timeline.audio_plan.final_fade is None


def test_one_photo_only_has_the_black_fades() -> None:
    timeline = compute_timeline(make_project([3.0], fade_from_black_s=1.0, fade_to_black_s=1.5))
    (slot,) = timeline.slots
    assert slot.fade_in is None and slot.fade_out is None
    assert (slot.visible_start, slot.visible_end) == (0.0, 3.0)
    assert timeline.fade_from_black is not None and timeline.fade_to_black is not None
    assert (timeline.fade_from_black.start, timeline.fade_from_black.end) == (0.0, 1.0)
    assert (timeline.fade_to_black.start, timeline.fade_to_black.end) == (1.5, 3.0)


def test_default_project_values() -> None:
    timeline = compute_timeline(make_project([None, None, 2.5]))
    assert [s.slot_start for s in timeline.slots] == [0.0, 2.0, 4.0]
    assert timeline.total_duration_s == 6.5
    assert timeline.total_frames == 195
    fade = timeline.slots[1].fade_in
    assert fade is not None and (fade.start, fade.end) == (1.5, 2.5)


def test_short_photos_shorten_their_crossfades() -> None:
    timeline = compute_timeline(make_project([1.0, 3.0, 1.2], crossfade_s=1.5))
    first, second = timeline.slots[1].fade_in, timeline.slots[2].fade_in
    assert first is not None and second is not None
    assert first.end - first.start == pytest.approx(0.5)
    assert second.end - second.start == pytest.approx(0.6)


def test_black_fades_longer_than_the_show_are_reduced_proportionally() -> None:
    timeline = compute_timeline(make_project([1.0, 1.5], fade_from_black_s=2.0, fade_to_black_s=3.0))
    fade_in, fade_out = timeline.fade_from_black, timeline.fade_to_black
    assert fade_in is not None and fade_out is not None
    assert fade_in.end == pytest.approx(1.0)  # 2.5 s of show, 5 s of fades: half of each
    assert fade_out.start == pytest.approx(1.0) and fade_out.end == 2.5


def test_zero_black_fades_are_absent() -> None:
    timeline = compute_timeline(make_project([2.0, 2.0], fade_from_black_s=0.0, fade_to_black_s=0.0))
    assert timeline.fade_from_black is None and timeline.fade_to_black is None


@given(projects(wide=True))
def test_black_fades_always_fit_in_the_show(project: Project) -> None:
    timeline = compute_timeline(project)
    total = timeline.total_duration_s
    lengths = 0.0
    for fade in (timeline.fade_from_black, timeline.fade_to_black):
        if fade is not None:
            assert 0.0 <= fade.start < fade.end <= total
            lengths += fade.end - fade.start
    assert lengths <= total + 1e-9
    wanted = project.fade_from_black_s + project.fade_to_black_s
    if wanted <= total and project.photos:
        assert lengths == pytest.approx(wanted, abs=1e-9)


def test_uses_the_requested_fps() -> None:
    timeline = compute_timeline(make_project([2.0, 2.0]), fps=25)
    assert timeline.fps == 25 and timeline.total_frames == 100
