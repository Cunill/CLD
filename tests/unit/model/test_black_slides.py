"""M08: the black slides stay first and last whatever is done to the photos; delete, put back, duration."""

from __future__ import annotations

from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from passimaker.model import (
    BLACK_END_ID,
    BLACK_START_ID,
    BlackSlide,
    BlackSlidePosition,
    Change,
    ProjectController,
    defaults,
    new_project,
)
from passimaker.model.commands import (
    AddBlackSlide,
    AddPhotos,
    AddSongs,
    DuplicatePhotos,
    FitToMusic,
    MovePhotos,
    RemovePhotos,
    RotatePhotos,
    SetPhotoDuration,
    SetPhotoFit,
    SetPhotoMotion,
    SortPhotos,
)
from passimaker.model.editing import visible_durations
from passimaker.model.types import FitMode, MotionType, Project, Rotation
from tests.unit.model.helpers import photo, photos, song

START, END = BlackSlidePosition.START, BlackSlidePosition.END


def with_blacks(count: int) -> ProjectController:
    controller = ProjectController(new_project(seed=7))
    if count:
        controller.execute(AddPhotos(photos(count)))
    return controller


def slide_ids(project: Project) -> list[str]:
    return [s.id for s in project.slides]


def assert_blacks_at_the_ends(project: Project) -> None:
    ids = slide_ids(project)
    assert ids[0] == BLACK_START_ID and ids[-1] == BLACK_END_ID
    assert ids.count(BLACK_START_ID) == 1 and ids.count(BLACK_END_ID) == 1


def test_a_new_project_has_two_black_slides_of_the_default_duration() -> None:
    project = new_project()
    assert project.slides == (BlackSlide(START), BlackSlide(END))
    assert project.black_start == BlackSlide(START) and project.black_end == BlackSlide(END)
    assert project.photos == ()
    assert defaults.BLACK_SLIDE_DURATION_S == 2.0
    duration_range = defaults.PHOTO_DURATION_RANGE
    assert duration_range.clamp(defaults.BLACK_SLIDE_DURATION_S) == defaults.BLACK_SLIDE_DURATION_S
    assert Project().slides == ()  # old files and Project() have none


def test_photos_are_the_slides_without_the_black_ones() -> None:
    controller = with_blacks(3)
    project = controller.project
    assert slide_ids(project) == [BLACK_START_ID, "p000", "p001", "p002", BLACK_END_ID]
    assert [p.id for p in project.photos] == ["p000", "p001", "p002"]


def test_added_photos_go_between_the_black_slides() -> None:
    controller = with_blacks(2)
    controller.execute(AddPhotos((photo("first"),), index=0))
    controller.execute(AddPhotos((photo("last"),)))
    controller.execute(AddPhotos((photo("far"),), index=99))
    project = controller.project
    assert slide_ids(project) == [BLACK_START_ID, "first", "p000", "p001", "last", "far", BLACK_END_ID]


def test_a_photo_cannot_take_the_id_of_a_black_slide() -> None:
    controller = with_blacks(0)
    controller.execute(AddPhotos((photo(BLACK_START_ID),)))
    assert_blacks_at_the_ends(controller.project)
    assert controller.project.photos[0].id != BLACK_START_ID


def test_moving_photos_never_moves_the_black_slides() -> None:
    controller = with_blacks(4)
    controller.execute(MovePhotos(("p003",), 0))
    controller.execute(MovePhotos(("p000",), 99))
    controller.execute(MovePhotos((BLACK_START_ID, BLACK_END_ID, "p001"), 0))
    project = controller.project
    assert slide_ids(project) == [BLACK_START_ID, "p001", "p003", "p002", "p000", BLACK_END_ID]


def test_sorting_and_duplicating_keep_the_black_slides_at_the_ends() -> None:
    controller = with_blacks(0)
    controller.execute(
        AddPhotos(
            (
                photo("b", name="IMG_10.jpg", taken=datetime(2024, 1, 2)),
                photo("a", name="IMG_2.jpg", taken=datetime(2024, 1, 3)),
            )
        )
    )
    controller.execute(SortPhotos(by_date=False))
    assert slide_ids(controller.project) == [BLACK_START_ID, "a", "b", BLACK_END_ID]
    controller.execute(SortPhotos(by_date=True))
    assert slide_ids(controller.project) == [BLACK_START_ID, "b", "a", BLACK_END_ID]
    controller.execute(DuplicatePhotos(("a", BLACK_END_ID, BLACK_START_ID)))
    assert slide_ids(controller.project) == [BLACK_START_ID, "b", "a", "a~2", BLACK_END_ID]


def test_photo_commands_ignore_the_black_slides() -> None:
    controller = with_blacks(1)
    blacks = frozenset({BLACK_START_ID, BLACK_END_ID})
    before = controller.project
    assert controller.execute(RotatePhotos(blacks, Rotation.R90)) == frozenset()
    assert controller.execute(SetPhotoFit(blacks, FitMode.BLACK)) == frozenset()
    controller.execute(SetPhotoMotion(blacks, MotionType.ZOOM_IN))
    after = controller.project
    assert after.slides[0] == before.slides[0] and after.slides[-1] == before.slides[-1]


def test_a_black_slide_is_deleted_like_a_photo_and_put_back_from_the_menu() -> None:
    controller = with_blacks(2)
    changes = controller.execute(RemovePhotos(frozenset({BLACK_START_ID, "p000"})))
    assert Change.PHOTOS in changes and Change.TIMING in changes
    assert slide_ids(controller.project) == ["p001", BLACK_END_ID]
    assert controller.project.black_start is None
    controller.execute(RemovePhotos(frozenset({BLACK_END_ID})))
    assert slide_ids(controller.project) == ["p001"]
    assert {Change.PHOTOS, Change.TIMING} <= controller.execute(AddBlackSlide(END))
    controller.execute(AddBlackSlide(START))
    assert slide_ids(controller.project) == [BLACK_START_ID, "p001", BLACK_END_ID]
    assert controller.project.black_start == BlackSlide(START)
    # Already there: nothing changes, no undo step.
    assert controller.execute(AddBlackSlide(START)) == frozenset()
    controller.execute(AddPhotos((photo("new"),), index=0))
    assert slide_ids(controller.project) == [BLACK_START_ID, "new", "p001", BLACK_END_ID]


def test_the_black_slide_duration_is_set_like_a_photo_duration() -> None:
    controller = with_blacks(1)
    changes = controller.execute(SetPhotoDuration(frozenset({BLACK_START_ID, "p000"}), 5.0))
    assert Change.TIMING in changes
    project = controller.project
    assert project.black_start == BlackSlide(START, 5.0)
    assert project.photos[0].duration_s == 5.0
    assert project.black_end == BlackSlide(END)
    controller.execute(SetPhotoDuration(frozenset({BLACK_END_ID}), 999.0))
    assert controller.project.black_end == BlackSlide(END, defaults.PHOTO_DURATION_RANGE.maximum)
    controller.execute(SetPhotoDuration(frozenset({BLACK_START_ID, BLACK_END_ID, "p000"}), None))
    project = controller.project
    assert project.black_start == BlackSlide(START) and project.black_end == BlackSlide(END)
    assert project.photos[0].duration_s is None
    assert project.photo_duration(BlackSlide(START, 3.0)) == 3.0


def test_undo_and_redo_bring_the_black_slides_back() -> None:
    controller = with_blacks(2)
    original = controller.project
    controller.execute(RemovePhotos(frozenset({BLACK_START_ID, BLACK_END_ID})))
    controller.execute(AddBlackSlide(START))
    controller.execute(SetPhotoDuration(frozenset({BLACK_START_ID}), 4.0))
    controller.undo()
    controller.undo()
    assert slide_ids(controller.project) == ["p000", "p001"]
    controller.undo()
    assert controller.project == original
    controller.redo()
    controller.redo()
    controller.redo()
    assert controller.project.black_start == BlackSlide(START, 4.0)
    assert controller.project.black_end is None


def test_the_photos_next_to_a_black_slide_have_a_crossfade_with_it() -> None:
    project = with_blacks(2).project
    # 2 s photos, 1 s crossfades: each photo gets half of the one on each side, the black ones included.
    assert visible_durations(project) == [3.0, 3.0]
    alone = ProjectController(Project(seed=7))
    alone.execute(AddPhotos(photos(2)))
    assert visible_durations(alone.project) == [2.5, 2.5]


def test_fit_to_music_leaves_the_black_slides_and_their_time_alone() -> None:
    controller = with_blacks(5)
    controller.execute(AddSongs((song("s", 14.0),)))
    controller.execute(FitToMusic())
    project = controller.project
    assert project.black_start == BlackSlide(START) and project.black_end == BlackSlide(END)
    total = sum(project.photo_duration(s) for s in project.slides)
    assert total == pytest.approx(14.0)


_ACTIONS = st.lists(
    st.one_of(
        st.builds(lambda i: AddPhotos((photo(f"n{i}"),), index=i % 5), st.integers(0, 50)),
        st.builds(lambda i, t: MovePhotos((f"p{i:03d}",), t), st.integers(0, 4), st.integers(0, 6)),
        st.builds(lambda i: DuplicatePhotos((f"p{i:03d}",)), st.integers(0, 4)),
        st.builds(lambda by_date: SortPhotos(by_date), st.booleans()),
        st.builds(lambda i: RemovePhotos(frozenset({f"p{i:03d}"})), st.integers(0, 4)),
    ),
    max_size=8,
)


@settings(max_examples=40, deadline=None)
@given(_ACTIONS)
def test_no_photo_command_takes_the_black_slides_from_the_ends(actions: list[object]) -> None:
    controller = with_blacks(5)
    for action in actions:
        controller.execute(action)  # type: ignore[arg-type]
        assert_blacks_at_the_ends(controller.project)
