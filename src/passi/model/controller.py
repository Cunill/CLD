"""Project controller: the only place where the project changes (block B1)."""

from __future__ import annotations

from collections.abc import Callable

from passi.model.commands import Change, Command
from passi.model.types import Project

type Observer = Callable[[frozenset[Change]], None]


class ProjectController:
    """Holds the current project, applies commands, notifies observers, keeps undo history.

    Contract:
    - execute(command) applies the command, clamps values to the ranges in defaults.py,
      pushes the previous project on the undo stack and notifies observers with the set
      of changes. Returns that set.
    - undo()/redo() restore snapshots and notify observers.
    - mark_saved() clears the "unsaved changes" flag.
    """

    def __init__(self, project: Project | None = None) -> None:
        raise NotImplementedError("B1")

    @property
    def project(self) -> Project:
        raise NotImplementedError("B1")

    @property
    def has_unsaved_changes(self) -> bool:
        raise NotImplementedError("B1")

    @property
    def can_undo(self) -> bool:
        raise NotImplementedError("B1")

    @property
    def can_redo(self) -> bool:
        raise NotImplementedError("B1")

    def subscribe(self, observer: Observer) -> Callable[[], None]:
        """Registers an observer; returns a function that unsubscribes it."""
        raise NotImplementedError("B1")

    def execute(self, command: Command) -> frozenset[Change]:
        raise NotImplementedError("B1")

    def undo(self) -> frozenset[Change]:
        raise NotImplementedError("B1")

    def redo(self) -> frozenset[Change]:
        raise NotImplementedError("B1")

    def replace_project(self, project: Project) -> None:
        """Loads a new project (open/recover); clears history and the unsaved flag."""
        raise NotImplementedError("B1")

    def mark_saved(self) -> None:
        raise NotImplementedError("B1")
