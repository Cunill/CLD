"""M09: shuffling the photos at random; deterministic, black slides in place, one undo step."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from passimaker.model import BLACK_END_ID, BLACK_START_ID, Change, ProjectController, new_project
from passimaker.model.commands import AddPhotos, RemovePhotos, ShufflePhotos
from passimaker.model.types import Project
from tests.unit.model.helpers import photos


def controller_with(count: int, seed: int = 7) -> ProjectController:
    controller = ProjectController(new_project(seed=seed))
    if count:
        controller.execute(AddPhotos(photos(count)))
    return controller


def slide_ids(project: Project) -> list[str]:
    return [s.id for s in project.slides]


def test_shuffling_gives_another_order_with_the_same_photos_and_the_black_slides_in_place() -> None:
    controller = controller_with(10)
    before = slide_ids(controller.project)
    controller.execute(ShufflePhotos())
    after = slide_ids(controller.project)
    assert after != before
    assert sorted(after) == sorted(before)
    assert after[0] == BLACK_START_ID and after[-1] == BLACK_END_ID


def test_every_press_gives_a_new_order() -> None:
    controller = controller_with(8)
    seen = {tuple(slide_ids(controller.project))}
    for _ in range(5):
        controller.execute(ShufflePhotos())
        seen.add(tuple(slide_ids(controller.project)))
    assert len(seen) == 6


def test_two_photos_always_swap() -> None:
    controller = controller_with(2)
    controller.execute(ShufflePhotos())
    assert [p.id for p in controller.project.photos] == ["p001", "p000"]
    controller.execute(ShufflePhotos())
    assert [p.id for p in controller.project.photos] == ["p000", "p001"]


def test_the_same_project_shuffles_the_same_way() -> None:
    first, second = controller_with(10), controller_with(10)
    first.execute(ShufflePhotos())
    second.execute(ShufflePhotos())
    assert slide_ids(first.project) == slide_ids(second.project)
    other_seed = controller_with(10, seed=99)
    other_seed.execute(ShufflePhotos())
    assert slide_ids(other_seed.project) != slide_ids(first.project)


def test_fewer_than_two_photos_do_nothing() -> None:
    for count in (0, 1):
        controller = controller_with(count)
        before, could_undo = controller.project, controller.can_undo
        assert controller.execute(ShufflePhotos()) == frozenset()
        assert controller.project is before and controller.can_undo == could_undo


def test_one_undo_step_and_redo() -> None:
    controller = controller_with(6)
    original = controller.project
    changes = controller.execute(ShufflePhotos())
    shuffled = controller.project
    assert Change.PHOTOS in changes
    controller.undo()
    assert controller.project == original
    controller.redo()
    assert controller.project == shuffled


def test_the_motions_follow_the_new_neighbours() -> None:
    controller = controller_with(10)
    controller.execute(ShufflePhotos())
    assert all(p.motion is not None for p in controller.project.photos)


@settings(max_examples=40, deadline=None)
@given(count=st.integers(0, 12), seed=st.integers(0, 1000), presses=st.integers(1, 3), removed=st.booleans())
def test_shuffling_keeps_the_photos_and_the_black_slides(
    count: int, seed: int, presses: int, removed: bool
) -> None:
    controller = controller_with(count, seed)
    if removed:
        controller.execute(RemovePhotos(frozenset({BLACK_END_ID})))
    before = controller.project
    for _ in range(presses):
        controller.execute(ShufflePhotos())
    after = controller.project
    assert sorted(slide_ids(after)) == sorted(slide_ids(before))
    assert after.black_start == before.black_start and after.black_end == before.black_end
    if before.black_start is not None:
        assert after.slides[0] == before.black_start
    if before.black_end is not None:
        assert after.slides[-1] == before.black_end
