"""B1: properties of random editing sessions (Hypothesis)."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from passimaker.model import Change, ProjectController
from passimaker.model import defaults as d
from passimaker.model.commands import (
    AddPhotos,
    AddSongs,
    Command,
    DuplicatePhotos,
    MovePhotos,
    MoveSongs,
    RemovePhotos,
    RemoveSongs,
    RerollMotions,
    RotatePhotos,
    SetDefaultDuration,
    SetPhotoDuration,
    SetPhotoFit,
    SetPhotoMotion,
    SetProjectSettings,
    SortPhotos,
)
from passimaker.model.editing import changes_between
from passimaker.model.types import FitMode, MotionType, OutputFormat, Project, Rotation
from passimaker.motion import base_window, is_inside, resolve_fit
from tests.unit.model.helpers import photo, song

POOL = [f"p{i}" for i in range(8)]
sizes = st.sampled_from([(4000, 3000), (3000, 4000), (6000, 2000), (2000, 2000), (800, 600)])
id_sets = st.frozensets(st.sampled_from(POOL), max_size=4)
id_lists = st.lists(st.sampled_from(POOL), max_size=3, unique=True).map(tuple)
seconds = st.floats(-5, 10, allow_nan=False)

commands: st.SearchStrategy[Command] = st.one_of(
    st.builds(
        lambda chosen, size, index: AddPhotos(tuple(photo(pid, *size) for pid in chosen), index),
        id_lists,
        sizes,
        st.none() | st.integers(-2, 10),
    ),
    st.builds(RemovePhotos, id_sets),
    st.builds(MovePhotos, id_lists, st.integers(-2, 12)),
    st.builds(DuplicatePhotos, id_lists),
    st.builds(SortPhotos, st.booleans()),
    st.builds(SetDefaultDuration, seconds),
    st.builds(SetPhotoDuration, id_sets, st.none() | seconds),
    st.builds(SetPhotoFit, id_sets, st.sampled_from(FitMode)),
    st.builds(SetPhotoMotion, id_sets, st.none() | st.sampled_from(MotionType)),
    st.builds(RerollMotions, st.none() | id_sets),
    st.builds(RotatePhotos, id_sets, st.sampled_from(Rotation)),
    st.builds(
        SetProjectSettings,
        output_format=st.none() | st.sampled_from(OutputFormat),
        crossfade_s=st.none() | seconds,
        zoom_amount=st.none() | st.floats(-1, 1),
    ),
    st.builds(lambda sid, length: AddSongs((song(sid, length),)), st.sampled_from("abc"), st.floats(1, 600)),
    st.builds(RemoveSongs, st.frozensets(st.sampled_from(["a", "b", "c"]))),
    st.builds(MoveSongs, st.lists(st.sampled_from("abc"), unique=True).map(tuple), st.integers(0, 4)),
)


def check_invariants(project: Project) -> None:
    photo_ids = [p.id for p in project.photos]
    assert len(set(photo_ids)) == len(photo_ids)
    assert len({s.id for s in project.music.songs}) == len(project.music.songs)
    assert d.PHOTO_DURATION_RANGE.minimum <= project.default_duration_s <= d.PHOTO_DURATION_RANGE.maximum
    assert d.CROSSFADE_RANGE.minimum <= project.crossfade_s <= d.CROSSFADE_RANGE.maximum
    assert d.MOTION_AMOUNT_RANGE.minimum <= project.zoom_amount <= d.MOTION_AMOUNT_RANGE.maximum
    for p in project.photos:
        duration = project.photo_duration(p)
        assert d.PHOTO_DURATION_RANGE.minimum <= duration <= d.PHOTO_DURATION_RANGE.maximum
        fit = resolve_fit(p.width, p.height, project.output_format, p.fit)
        assert p.motion.resolved_fit is fit.fit
        base = base_window(fit.canvas_width, fit.canvas_height, project.output_format)
        assert is_inside(p.motion.start, base) and is_inside(p.motion.end, base)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(commands, max_size=12), st.integers(0, 2**31))
def test_random_sessions_keep_the_project_valid_and_undoable(sequence: list[Command], seed: int) -> None:
    controller = ProjectController(Project(seed=seed))
    history = [controller.project]
    for command in sequence:
        before = controller.project
        changes = controller.execute(command)
        after = controller.project
        assert bool(changes) == (after is not before)
        assert changes - {Change.SAVED_STATE} == changes_between(before, after)
        check_invariants(after)
        if after is not before:
            history.append(after)
    while controller.can_undo:
        history.pop()
        controller.undo()
        assert controller.project is history[-1]
    assert not controller.has_unsaved_changes


@settings(max_examples=25, deadline=None)
@given(st.lists(commands, max_size=8), st.integers(0, 1000))
def test_editing_is_deterministic(sequence: list[Command], seed: int) -> None:
    first, second = ProjectController(Project(seed=seed)), ProjectController(Project(seed=seed))
    for command in sequence:
        first.execute(command)
        second.execute(command)
    assert first.project == second.project
