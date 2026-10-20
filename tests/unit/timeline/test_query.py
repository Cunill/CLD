"""B2 · What is on screen at time t (contract: Visibles)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from passi.model.types import Project
from passi.timeline import Timeline, compute_timeline, query
from tests.unit.timeline.helpers import make_project, projects


def sample_times(timeline: Timeline, count: int = 400) -> list[float]:
    """Evenly spaced instants plus every fade boundary (where the edge cases are)."""
    total = timeline.total_duration_s
    times = [total * i / count for i in range(count + 1)]
    for slot in timeline.slots:
        times += [slot.slot_start, slot.slot_end, slot.visible_start, slot.visible_end]
    for fade in (timeline.fade_from_black, timeline.fade_to_black):
        if fade is not None:
            times += [fade.start, fade.end]
    return sorted(t for t in times if 0.0 <= t <= total)


def in_black_fade(timeline: Timeline, t: float) -> bool:
    fades = (timeline.fade_from_black, timeline.fade_to_black)
    return any(f is not None and f.start < t < f.end for f in fades)


@given(projects(min_photos=1, wide=True))
def test_opacities_add_up_to_one_and_at_most_two_photos_are_visible(project: Project) -> None:
    timeline = compute_timeline(project)
    for t in sample_times(timeline):
        visibles = query(timeline, t)
        assert 1 <= len(visibles.layers) <= 2
        assert sum(layer.opacity for layer in visibles.layers) == pytest.approx(1.0, abs=1e-9)
        assert all(0.0 < layer.opacity <= 1.0 for layer in visibles.layers)
        assert 0.0 <= visibles.black_level <= 1.0
        if not in_black_fade(timeline, t) and timeline.fade_to_black is not None:
            assert visibles.black_level in (0.0, 1.0)
        if not in_black_fade(timeline, t):
            assert visibles.black_level == 0.0 or t in (0.0, timeline.total_duration_s)


@given(projects(min_photos=2, wide=True))
def test_layers_are_consecutive_photos_with_the_outgoing_one_below(project: Project) -> None:
    timeline = compute_timeline(project)
    order = {slot.photo_id: slot.index for slot in timeline.slots}
    for t in sample_times(timeline):
        layers = query(timeline, t).layers
        if len(layers) == 2:
            assert order[layers[1].photo_id] == order[layers[0].photo_id] + 1


@given(projects(min_photos=1, wide=True))
def test_motion_progress_goes_from_0_to_1_continuously_over_the_visible_span(project: Project) -> None:
    timeline = compute_timeline(project)
    for slot in timeline.slots:
        span = slot.visible_end - slot.visible_start
        steps = 50
        previous = -1.0
        for i in range(steps + 1):
            t = slot.visible_start + span * i / steps
            if i == steps:
                t = slot.visible_end
            layer = next((x for x in query(timeline, t).layers if x.photo_id == slot.photo_id), None)
            if layer is None:  # opacity 0: the very first instant of a fade-in or the last of a fade-out
                assert i in (0, steps)
                continue
            assert layer.motion_progress == pytest.approx(i / steps, abs=1e-9)
            assert layer.motion_progress > previous
            previous = layer.motion_progress


def test_crossfade_is_linear_and_centred_on_the_change() -> None:
    timeline = compute_timeline(make_project([2.0, 2.0], fade_from_black_s=0.0, fade_to_black_s=0.0))
    at_change = query(timeline, 2.0).layers
    assert [(x.photo_id, x.opacity) for x in at_change] == [("p0", 0.5), ("p1", 0.5)]
    quarter = query(timeline, 1.75).layers
    assert [x.photo_id for x in quarter] == ["p0", "p1"]
    assert quarter[1].opacity == pytest.approx(0.25)
    assert [x.photo_id for x in query(timeline, 1.4).layers] == ["p0"]
    assert [x.photo_id for x in query(timeline, 2.5).layers] == ["p1"]


def test_black_fades_ramp_linearly() -> None:
    timeline = compute_timeline(make_project([2.0, 2.0, 2.0]))
    assert query(timeline, 0.0).black_level == 1.0
    assert query(timeline, 0.25).black_level == pytest.approx(0.75)
    assert query(timeline, 1.0).black_level == 0.0
    assert query(timeline, 3.0).black_level == 0.0
    assert query(timeline, 5.0).black_level == pytest.approx(0.5)
    end = query(timeline, 6.0)
    assert end.black_level == 1.0
    assert [(x.photo_id, x.motion_progress) for x in end.layers] == [("p2", 1.0)]


def test_without_fade_to_black_the_last_instant_shows_the_last_photo() -> None:
    timeline = compute_timeline(make_project([2.0], fade_from_black_s=0.0, fade_to_black_s=0.0))
    assert query(timeline, 0.0).black_level == 0.0
    end = query(timeline, 2.0)
    assert end.black_level == 0.0 and [x.photo_id for x in end.layers] == ["p0"]


@given(st.floats(allow_nan=False, allow_infinity=False).filter(lambda t: t < 0 or t > 6))
def test_outside_the_show_it_is_black(t: float) -> None:
    timeline = compute_timeline(make_project([2.0, 2.0, 2.0]))
    visibles = query(timeline, t)
    assert visibles.layers == () and visibles.black_level == 1.0


def test_empty_timeline_is_black() -> None:
    visibles = query(compute_timeline(Project()), 0.0)
    assert visibles.layers == () and visibles.black_level == 1.0


def test_query_scales_to_long_shows() -> None:
    timeline = compute_timeline(make_project([None] * 3600))
    t = 3599 * 2.0 + 1.0  # after the last crossfade
    (layer,) = query(timeline, t).layers
    assert layer.photo_id == "p3599"
