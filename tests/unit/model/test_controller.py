"""B1: controller history (undo/redo, P1), observers and the "unsaved changes" flag."""

from __future__ import annotations

from passimaker.model import Change, ProjectController
from passimaker.model.commands import AddPhotos, RemovePhotos, SetDefaultDuration, SetProjectSettings
from passimaker.model.defaults import UNDO_HISTORY_STEPS
from passimaker.model.types import Project
from tests.unit.model.helpers import controller_with, ids, photos


def test_new_controller_has_an_empty_saved_project() -> None:
    controller = ProjectController()
    assert controller.project == Project()
    assert not controller.has_unsaved_changes
    assert not controller.can_undo and not controller.can_redo


def test_execute_returns_the_changes_and_notifies_observers() -> None:
    controller = ProjectController()
    received: list[frozenset[Change]] = []
    controller.subscribe(received.append)
    changes = controller.execute(SetProjectSettings(name="Vacances"))
    assert changes == {Change.SETTINGS, Change.SAVED_STATE}
    assert received == [changes]
    assert controller.project.name == "Vacances"
    assert controller.has_unsaved_changes


def test_saved_state_is_only_reported_when_the_flag_flips() -> None:
    controller = ProjectController()
    controller.execute(SetProjectSettings(name="a"))
    assert controller.execute(SetProjectSettings(name="b")) == {Change.SETTINGS}


def test_unsubscribe_stops_notifications() -> None:
    controller = ProjectController()
    received: list[frozenset[Change]] = []
    unsubscribe = controller.subscribe(received.append)
    unsubscribe()
    unsubscribe()  # idempotent
    controller.execute(SetProjectSettings(name="x"))
    assert received == []


def test_a_command_that_changes_nothing_is_not_recorded() -> None:
    controller = ProjectController()
    received: list[frozenset[Change]] = []
    controller.subscribe(received.append)
    assert controller.execute(SetDefaultDuration(2.0)) == frozenset()
    assert controller.execute(RemovePhotos(frozenset({"nobody"}))) == frozenset()
    assert not controller.can_undo
    assert not controller.has_unsaved_changes
    assert received == []


def test_undo_and_redo_restore_snapshots() -> None:
    controller = controller_with(3)
    original = controller.project
    controller.execute(RemovePhotos(frozenset({"p001"})))
    removed = controller.project
    assert ids(removed) == ["p000", "p002"]

    assert Change.PHOTOS in controller.undo()
    assert controller.project is original
    assert controller.can_redo and not controller.can_undo

    assert Change.PHOTOS in controller.redo()
    assert controller.project is removed
    assert controller.undo() and controller.undo() == frozenset()


def test_a_new_command_clears_the_redo_stack() -> None:
    controller = controller_with(2)
    controller.execute(SetDefaultDuration(3.0))
    controller.undo()
    controller.execute(SetDefaultDuration(1.5))
    assert not controller.can_redo
    assert controller.redo() == frozenset()


def test_undo_back_to_the_saved_state_clears_the_unsaved_flag() -> None:
    controller = controller_with(2)
    controller.execute(SetDefaultDuration(3.0))
    assert controller.has_unsaved_changes
    assert Change.SAVED_STATE in controller.undo()
    assert not controller.has_unsaved_changes
    assert Change.SAVED_STATE in controller.redo()
    assert controller.has_unsaved_changes


def test_mark_saved_clears_the_flag_and_notifies() -> None:
    controller = ProjectController()
    controller.execute(SetProjectSettings(name="x"))
    received: list[frozenset[Change]] = []
    controller.subscribe(received.append)
    controller.mark_saved()
    controller.mark_saved()  # nothing to report the second time
    assert not controller.has_unsaved_changes
    assert received == [frozenset({Change.SAVED_STATE})]
    assert controller.can_undo  # saving does not touch the history (§1.13)


def test_replace_project_clears_history_and_flag() -> None:
    controller = ProjectController()
    controller.execute(AddPhotos(photos(2)))
    received: list[frozenset[Change]] = []
    controller.subscribe(received.append)
    opened = Project(name="obert")
    controller.replace_project(opened)
    assert controller.project is opened
    assert not controller.can_undo and not controller.can_redo
    assert not controller.has_unsaved_changes
    assert received == [frozenset(Change)]


def test_history_keeps_the_last_100_steps() -> None:
    controller = ProjectController()
    for i in range(UNDO_HISTORY_STEPS + 20):
        controller.execute(SetProjectSettings(name=str(i)))
    steps = 0
    while controller.can_undo:
        controller.undo()
        steps += 1
    assert steps == UNDO_HISTORY_STEPS
    assert controller.project.name == "19"
