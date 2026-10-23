"""Saving and opening projects (§1.10): Desar, Desar com a, Obrir, Recents, recovery and relinking.

``ProjectFiles`` keeps the file the project came from, the list of recent projects (QSettings),
and the recovery copy written every two minutes outside the project folder. It talks to
``passimaker.projectio`` and to the controller only (rule 2): an opened, recovered or relinked
project enters through ``replace_project``.

Two cases leave the project different from any file even though the controller's history is
new: a recovered copy and a relinked project. ``modified`` covers them with its own flag, so the
title shows the asterisk and closing asks to save.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, cast

from PySide6.QtCore import QObject, QRunnable, QSettings, QStandardPaths, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from passimaker.common import PassiMakerError
from passimaker.export import cache_root
from passimaker.i18n import message
from passimaker.model import Change, Project, ProjectController, defaults
from passimaker.projectio import (
    EXTENSION,
    clear_recovery,
    find_recovery,
    open_project,
    relink,
    save_project,
    save_recovery,
)

RECENT_KEY = "projectes_recents"
MAX_RECENT = 8
"""Recent projects kept in the File menu and on the empty screen."""
RECOVERY_FOLDER = "recuperacio"
"""Inside cache_root(): §1.10, the recovery copy lives outside the project folder."""
ORGANISATION = "PassiMaker"
APPLICATION = "PassiMaker"


class SaveAnswer(Enum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class FileQuestions(Protocol):
    """What saving and opening ask the user."""

    def choose_project_to_open(self) -> Path | None: ...

    def choose_project_save_path(self, suggested: Path) -> Path | None: ...

    def ask_save_changes(self, name: str) -> SaveAnswer:
        """ "Vols desar els canvis de «nom»?" [Desar] [No desar] [Cancel·lar]."""
        ...

    def offer_recovery(self) -> bool:
        """§1.10: after a crash, "Vols recuperar el projecte?"."""
        ...

    def ask_relink(self, count: int) -> Path | None:
        """ "No es troben 12 fitxers. [Cercar en una carpeta…]": the folder chosen, or None."""
        ...

    def choose_folder(self) -> Path | None: ...

    def report_relinked(self, found: int, still_missing: int) -> None: ...

    def show_error(self, text: str) -> None: ...


def user_settings() -> QSettings:
    """An INI file in the user's folder (%APPDATA%\\PassiMaker on Windows), not the registry: the
    program is a portable ZIP and leaves nothing behind that a folder cannot hold."""
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, ORGANISATION, APPLICATION)


def default_recovery_dir() -> Path:
    return cache_root() / RECOVERY_FOLDER


def with_extension(path: Path) -> Path:
    return path if path.suffix.lower() == EXTENSION else path.with_name(path.name + EXTENSION)


@dataclass(frozen=True, slots=True)
class _Relinked:
    source: Project
    """The project the search started from: if it is no longer the current one, search again."""
    project: Project
    found: int
    still_missing: tuple[Path, ...]


class _RelinkSignals(QObject):
    done = Signal(object)


class _Relink(QRunnable):
    def __init__(self, project: Project, folder: Path, signals: _RelinkSignals) -> None:
        super().__init__()
        self._project = project
        self._folder = folder
        self._signals = signals

    def run(self) -> None:
        project, found = relink(self._project, self._folder)
        items = (*project.photos, *project.music.songs)
        still = tuple(dict.fromkeys(item.path for item in items if not item.path.exists()))
        self._signals.done.emit(_Relinked(self._project, project, found, still))


class ProjectFiles(QObject):
    """The file behind the project, the recent list and the recovery copy."""

    state_changed = Signal()
    """The file, its name or the "unsaved changes" state changed (title of the window)."""
    recent_changed = Signal()
    missing_changed = Signal()
    """The set of photos and songs whose file is not found changed."""
    relinked = Signal(int)
    """A search in a folder ended; how many files were found."""

    def __init__(
        self,
        controller: ProjectController,
        questions: FileQuestions,
        *,
        recovery_dir: Path | None = None,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._questions = questions
        self.recovery_dir = recovery_dir if recovery_dir is not None else default_recovery_dir()
        self._settings = settings if settings is not None else user_settings()
        self.path: Path | None = None
        self._detached = False
        """True for a recovered or relinked project: it differs from its file whatever the history says."""
        self.missing: tuple[Path, ...] = ()
        self._relink_folder: Path | None = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._unsubscribe = controller.subscribe(self._on_changes)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(int(defaults.AUTOSAVE_INTERVAL_S * 1000))
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

    # --- State -----------------------------------------------------------------------------------

    @property
    def modified(self) -> bool:
        return self._controller.has_unsaved_changes or self._detached

    def display_name(self) -> str:
        if self.path is not None:
            return self.path.stem
        return self._controller.project.name or self.tr("Sense títol")

    def window_title(self) -> str:
        """ "nom[*] — PassiMaker": Qt shows the asterisk where [*] is when the window is modified."""
        return self.tr("{name}[*] — PassiMaker").format(name=self.display_name())

    def missing_ids(self) -> frozenset[str]:
        if not self.missing:
            return frozenset()
        lost = set(self.missing)
        project = self._controller.project
        return frozenset(item.id for item in (*project.photos, *project.music.songs) if item.path in lost)

    # --- Saving ----------------------------------------------------------------------------------

    def save(self) -> bool:
        """Ctrl+S. Without a file yet it is "Desar com a…". False if nothing was saved."""
        if self.path is None:
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        suggested = self.path if self.path is not None else self._suggested_path()
        chosen = self._questions.choose_project_save_path(suggested)
        if chosen is None:
            return False
        return self._write(with_extension(chosen))

    def _suggested_path(self) -> Path:
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        base = Path(folder) if folder else Path.home()
        return base / f"{self.display_name()}{EXTENSION}"

    def _write(self, path: Path) -> bool:
        try:
            save_project(self._controller.project, path)
        except PassiMakerError as error:
            self._questions.show_error(message(error.message_key))
            return False
        self.path = path
        self._detached = False
        self._controller.mark_saved()
        self._add_recent(path)
        self._clear_recovery()
        self.state_changed.emit()
        return True

    def maybe_save(self) -> bool:
        """§1.10: before closing or opening another project. False means "stay"."""
        if not self.modified:
            return True
        answer = self._questions.ask_save_changes(self.display_name())
        if answer is SaveAnswer.SAVE:
            return self.save()
        return answer is SaveAnswer.DISCARD

    # --- Opening ---------------------------------------------------------------------------------

    def open(self) -> bool:
        """Ctrl+O."""
        if not self.maybe_save():
            return False
        chosen = self._questions.choose_project_to_open()
        return chosen is not None and self.open_path(chosen, ask_to_save=False)

    def open_path(self, path: Path, *, ask_to_save: bool = True) -> bool:
        """Opens a .pmk (recent list, argument of the program, file dropped on the window)."""
        if ask_to_save and not self.maybe_save():
            return False
        try:
            opened = open_project(path)
        except PassiMakerError as error:
            self._questions.show_error(message(error.message_key))
            self.offer_recovery()  # §1.10: a damaged file offers the recovery copy, if there is one.
            return False
        self._load(opened.project, path, detached=False)
        self._add_recent(path)
        self._set_missing(opened.missing_files)
        if self.missing:
            folder = self._questions.ask_relink(len(self.missing))
            if folder is not None:
                self.relink_from(folder)
        return True

    def _load(self, project: Project, path: Path | None, *, detached: bool) -> None:
        self.path = path
        self._detached = detached
        self._controller.replace_project(project)
        self.state_changed.emit()

    # --- Missing files ---------------------------------------------------------------------------

    def find_missing(self, folder: Path | None = None) -> None:
        """ "Cercar en una carpeta…" from the status bar or the menu."""
        if not self.missing:
            return
        chosen = folder if folder is not None else self._questions.choose_folder()
        if chosen is not None:
            self.relink_from(chosen)

    def relink_from(self, folder: Path) -> None:
        """§1.10: finds the missing files by name inside the folder and its subfolders.

        Walking a big folder takes seconds, so it runs in a worker thread (rule 6); ``relinked``
        says when it is done.
        """
        self._relink_folder = folder
        signals = _RelinkSignals(self)
        signals.done.connect(self._on_relinked)
        self._pool.start(_Relink(self._controller.project, folder, signals))

    @property
    def relinking(self) -> bool:
        return self._relink_folder is not None

    def wait(self, milliseconds: int = 30_000) -> bool:
        """Waits for the worker thread (tests, closing the window)."""
        return self._pool.waitForDone(milliseconds)

    def _on_relinked(self, outcome: object) -> None:
        folder = self._relink_folder
        if not isinstance(outcome, _Relinked) or folder is None:
            return
        if outcome.source is not self._controller.project:
            self.relink_from(folder)  # edited meanwhile: search again on the current project
            return
        self._relink_folder = None
        if outcome.found:
            self._load(outcome.project, self.path, detached=True)
        self._set_missing(outcome.still_missing)
        self._questions.report_relinked(outcome.found, len(outcome.still_missing))
        self.relinked.emit(outcome.found)

    def _set_missing(self, paths: Sequence[Path]) -> None:
        missing = tuple(dict.fromkeys(paths))
        if missing != self.missing:
            self.missing = missing
            self.missing_changed.emit()

    # --- Recovery --------------------------------------------------------------------------------

    def autosave(self) -> None:
        """Every two minutes (§1.10), only if there is something that would be lost."""
        if not self.modified:
            return
        project = self._controller.project
        if not project.photos and not project.music.songs:
            return
        # A recovery copy that cannot be written must not interrupt the user.
        with suppress(PassiMakerError):
            save_recovery(project, self.recovery_dir)

    def offer_recovery(self) -> bool:
        """§1.10: after a crash, at start-up. True if a project was recovered."""
        found = find_recovery(self.recovery_dir)
        if found is None:
            return False
        if not self._questions.offer_recovery():
            self._clear_recovery()
            return False
        try:
            opened = open_project(found)
        except PassiMakerError as error:
            self._questions.show_error(message(error.message_key))
            self._clear_recovery()
            return False
        self._load(opened.project, None, detached=True)
        self._set_missing(opened.missing_files)
        return True

    def startup(self, argument: Path | None) -> None:
        """The program starts with a .pmk to open, or offers the recovery copy if there is one."""
        if argument is not None:
            self.open_path(argument, ask_to_save=False)
        else:
            self.offer_recovery()

    def shutdown(self) -> None:
        """A clean exit: the recovery copy is no longer needed."""
        self.autosave_timer.stop()
        self._relink_folder = None
        self.wait(5_000)
        self._unsubscribe()
        self._clear_recovery()

    def _clear_recovery(self) -> None:
        with suppress(PassiMakerError):
            clear_recovery(self.recovery_dir)

    # --- Recent projects -------------------------------------------------------------------------

    def recent(self) -> list[Path]:
        stored: object = self._settings.value(RECENT_KEY, [])
        values: list[object] = []
        if isinstance(stored, str):
            values = [stored]
        elif isinstance(stored, list):
            values = list(cast(list[object], stored))
        return [Path(str(value)) for value in values if value][:MAX_RECENT]

    def _add_recent(self, path: Path) -> None:
        absolute = path.absolute()
        paths = [absolute, *(p for p in self.recent() if p != absolute)][:MAX_RECENT]
        self._settings.setValue(RECENT_KEY, [str(p) for p in paths])
        self._settings.sync()
        self.recent_changed.emit()

    # --- Controller ------------------------------------------------------------------------------

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if Change.SAVED_STATE in changes or Change.SETTINGS in changes:
            self.state_changed.emit()
        if self.missing and changes & {Change.PHOTOS, Change.MUSIC}:
            self.missing_changed.emit()


class RecentProjects(QWidget):
    """§1.10: the recent projects on the empty screen."""

    open_requested = Signal(object)

    def __init__(self, files: ProjectFiles, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files = files
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 12, 0, 0)
        self.title = QLabel(self.tr("Projectes recents"))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.title)
        self.buttons: list[QPushButton] = []
        files.recent_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        for button in self.buttons:
            self._layout.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        for path in self._files.recent():
            button = QPushButton(path.stem)
            button.setFlat(True)
            button.setToolTip(str(path))
            button.clicked.connect(lambda _checked=False, p=path: self.open_requested.emit(p))
            self._layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
            self.buttons.append(button)
        self.setVisible(bool(self.buttons))


class MissingFilesBar(QWidget):
    """ "No es troben 12 fitxers. [Cercar en una carpeta…]" in the status bar (§1.10)."""

    def __init__(self, files: ProjectFiles, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files = files
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.button = QPushButton(self.tr("Cercar en una carpeta…"))
        self.button.setFlat(True)
        self.button.clicked.connect(lambda: files.find_missing())
        layout.addWidget(self.label)
        layout.addWidget(self.button)
        files.missing_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        count = len(self._files.missing_ids())
        self.label.setText(self.tr("No es troben {n} fitxers.").format(n=count))
        self.setVisible(count > 0)
