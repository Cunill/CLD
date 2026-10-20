"""Project controller: the only place where the project changes (block B1)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from passimaker.model import defaults
from passimaker.model.commands import Change, Command
from passimaker.model.editing import apply_command, changes_between
from passimaker.model.types import Project

type Observer = Callable[[frozenset[Change]], None]


class ProjectController:
    """Holds the current project, applies commands, notifies observers, keeps undo history.

    Contract:
    - execute(command) applies the command, clamps values to the ranges in defaults.py,
      pushes the previous project on the undo stack and notifies observers with the set
      of changes. Returns that set.
    - undo()/redo() restore snapshots and notify observers.
    - mark_saved() clears the "unsaved changes" flag.

    The project is immutable, so the history keeps whole snapshots (§1.13, P1). The "unsaved
    changes" flag compares the current snapshot with the last saved one, so undoing back to
    the saved state clears it.
    """

    def __init__(self, project: Project | None = None) -> None:
        self._project = project if project is not None else Project()
        self._saved = self._project
        self._undo: deque[Project] = deque(maxlen=defaults.UNDO_HISTORY_STEPS)
        self._redo: list[Project] = []
        self._observers: list[Observer] = []

    @property
    def project(self) -> Project:
        return self._project

    @property
    def has_unsaved_changes(self) -> bool:
        return self._project is not self._saved

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def subscribe(self, observer: Observer) -> Callable[[], None]:
        """Registers an observer; returns a function that unsubscribes it."""
        self._observers.append(observer)

        def unsubscribe() -> None:
            if observer in self._observers:
                self._observers.remove(observer)

        return unsubscribe

    def execute(self, command: Command) -> frozenset[Change]:
        edited = apply_command(self._project, command)
        if edited is self._project:
            return frozenset()
        self._undo.append(self._project)
        self._redo.clear()
        return self._switch_to(edited)

    def undo(self) -> frozenset[Change]:
        if not self._undo:
            return frozenset()
        self._redo.append(self._project)
        return self._switch_to(self._undo.pop())

    def redo(self) -> frozenset[Change]:
        if not self._redo:
            return frozenset()
        self._undo.append(self._project)
        return self._switch_to(self._redo.pop())

    def replace_project(self, project: Project) -> None:
        """Loads a new project (open/recover); clears history and the unsaved flag."""
        self._project = project
        self._saved = project
        self._undo.clear()
        self._redo.clear()
        self._notify(frozenset(Change))

    def mark_saved(self) -> None:
        if self.has_unsaved_changes:
            self._saved = self._project
            self._notify(frozenset({Change.SAVED_STATE}))

    def _switch_to(self, project: Project) -> frozenset[Change]:
        was_unsaved = self.has_unsaved_changes
        changes = changes_between(self._project, project)
        self._project = project
        if self.has_unsaved_changes != was_unsaved:
            changes.add(Change.SAVED_STATE)
        result = frozenset(changes)
        self._notify(result)
        return result

    def _notify(self, changes: frozenset[Change]) -> None:
        for observer in list(self._observers):
            observer(changes)
