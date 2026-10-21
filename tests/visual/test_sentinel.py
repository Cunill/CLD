"""B6 · Sentinel colour: no frame ever shows anything outside the photo canvas."""

from __future__ import annotations

from dataclasses import replace

import pytest

from passimaker.model.types import MotionType, OutputFormat, PhotoMotion, Project, ResolvedFit, Window
from passimaker.render import SENTINEL_COLOR
from passimaker.render import compositor as compositor_module
from tests.visual.helpers import (
    ALL_MOTIONS,
    build_project,
    compositor_for,
    frame_times,
    magenta_count,
    photo,
    synthetic_projects,
)

PROJECTS = synthetic_projects()


def _size(project: Project, long_side: int) -> tuple[int, int]:
    short = long_side * 9 // 16
    return (long_side, short) if project.output_format is OutputFormat.HORIZONTAL else (short, long_side)


def test_the_projects_cover_every_motion_fit_and_format() -> None:
    motions = {p.motion.type for project in PROJECTS.values() for p in project.photos}
    fits = {p.motion.resolved_fit for project in PROJECTS.values() for p in project.photos}
    formats = {project.output_format for project in PROJECTS.values()}
    assert motions == set(ALL_MOTIONS)
    assert fits == set(ResolvedFit)
    assert formats == set(OutputFormat)


@pytest.mark.parametrize("name", PROJECTS)
def test_no_sentinel_in_any_frame_at_480p(name: str) -> None:
    project = PROJECTS[name]
    compositor, timeline = compositor_for(project)
    width, height = _size(project, 480)
    bad = [
        round(t, 3)
        for t in frame_times(timeline)
        if magenta_count(compositor.frame_at(t, width, height, sentinel=True))
    ]
    assert bad == []


@pytest.mark.parametrize("name", PROJECTS)
def test_no_sentinel_in_100_frames_at_1080p(name: str) -> None:
    project = PROJECTS[name]
    compositor, timeline = compositor_for(project)
    width, height = _size(project, 1920)
    times = frame_times(timeline)
    step = max(1, len(times) // 100)
    sample = times[::step][:100]
    assert len(sample) == 100
    bad = [round(t, 3) for t in sample if magenta_count(compositor.frame_at(t, width, height, sentinel=True))]
    assert bad == []


def _too_wide_project() -> Project:
    """A 4:3 photo whose (hand-made) window is wider than the canvas."""
    project = build_project([photo("a", 4000, 3000)], motions={"a": MotionType.NONE})
    window = Window(0.5, 0.5, 0.8)
    motion = PhotoMotion(start=window, end=window, resolved_fit=ResolvedFit.FILL)
    return replace(project, photos=(replace(project.photos[0], motion=motion),))


def test_sentinel_paints_whatever_falls_outside_the_canvas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Positive control: a window larger than the canvas leaves magenta bands at the sides."""
    monkeypatch.setattr(compositor_module, "is_inside", lambda *_args, **_kw: True)
    compositor, timeline = compositor_for(_too_wide_project())
    middle = timeline.total_duration_s / 2
    frame = compositor.frame_at(middle, 480, 270, sentinel=True)
    assert tuple(int(c) for c in frame[135, 0]) == SENTINEL_COLOR
    assert tuple(int(c) for c in frame[135, 479]) == SENTINEL_COLOR
    assert magenta_count(frame[:, 100:380]) == 0
    normal = compositor.frame_at(middle, 480, 270)
    assert magenta_count(normal) == 0
    assert tuple(int(c) for c in normal[135, 0]) == (0, 0, 0)


def test_sentinel_is_painted_after_the_black_fades(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even an almost black frame shows the sentinel at full strength."""
    monkeypatch.setattr(compositor_module, "is_inside", lambda *_args, **_kw: True)
    compositor, _ = compositor_for(_too_wide_project())
    frame = compositor.frame_at(0.01, 480, 270, sentinel=True)
    assert tuple(int(c) for c in frame[135, 0]) == SENTINEL_COLOR
    assert int(frame[135, 240].max()) < 10


def test_a_motion_that_does_not_fit_the_canvas_is_shown_whole() -> None:
    project = build_project([photo("a", 4000, 3000)])
    motion = PhotoMotion(
        type=MotionType.PAN_LEFT,
        start=Window(0.1, 0.5, 1.0),
        end=Window(0.9, 0.5, 1.0),
        resolved_fit=ResolvedFit.FILL,
    )
    project = replace(project, photos=(replace(project.photos[0], motion=motion),))
    compositor, timeline = compositor_for(project)
    for t in frame_times(timeline, step=5):
        assert magenta_count(compositor.frame_at(t, 320, 180, sentinel=True)) == 0
