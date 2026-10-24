"""Importing photos without blocking the window (§1.1).

``passimaker.importer.import_paths`` reads the header of every file, which on a thousand photos
takes seconds: it runs in a worker thread and reports progress, and the only questions of §1.1
(subfolders, duplicates) are asked once each, between passes, on the GUI thread.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from passimaker.common import CancelToken
from passimaker.importer import FailedFile, ImportResult, PhotoCandidate, import_paths, sort_candidates
from passimaker.model import OutputFormat, Photo, ProjectController, defaults
from passimaker.model.commands import AddPhotos

_ids = itertools.count(1)
"""Photo ids are only unique inside a project; the controller renames a repeated one."""


def photo_from_candidate(candidate: PhotoCandidate, photo_id: str, output_format: OutputFormat) -> Photo:
    """A new photo with the default settings; its motion is drawn by the controller.

    Same rule as ``passimaker.cli.photo_from_candidate`` (the command line creates projects with
    the same steps as the interface); the shared helper belongs to a module both can import,
    which would change a contract and is proposed for a later block.
    """
    return Photo(
        id=photo_id,
        path=candidate.path,
        relative_path=None,
        width=candidate.width,
        height=candidate.height,
        exif_orientation=candidate.exif_orientation,
        capture_time=candidate.capture_time,
        # §1.1: short side under half the video's (540 px in 1080p) -> "low resolution" icon.
        low_resolution=2 * min(candidate.width, candidate.height) < min(output_format.size),
    )


class ImportQuestions(Protocol):
    """The questions and warnings of §1.1, asked on the GUI thread."""

    def ask_subfolders(self, count: int) -> bool:
        """ "Vols incloure també les subcarpetes (N fotos més)?"."""
        ...

    def ask_duplicates(self, count: int) -> bool:
        """ "N fotos ja hi són. Les vols afegir igualment?" (the default answer is no)."""
        ...

    def report_failures(self, failures: Sequence[FailedFile]) -> None:
        """ "2 fitxers no s'han pogut afegir [Veure quins]"."""
        ...

    def warn_many_photos(self, count: int) -> None:
        """ "Més de 1.000 fotos: el programa pot anar més lent"."""
        ...


@dataclass(slots=True)
class _Pass:
    """State kept between the passes of one import."""

    paths: tuple[Path, ...]
    index: int | None
    include_subfolders: bool = False
    allow_duplicates: bool = False
    asked_subfolders: bool = False
    asked_duplicates: bool = False


class _Signals(QObject):
    done = Signal(object)
    progress = Signal(int, int)


class _Scan(QRunnable):
    """One call to import_paths in a worker thread."""

    def __init__(
        self,
        paths: Sequence[Path],
        existing: frozenset[Path],
        include_subfolders: bool,
        cancel: CancelToken,
        signals: _Signals,
    ) -> None:
        super().__init__()
        self._paths = tuple(paths)
        self._existing = existing
        self._include_subfolders = include_subfolders
        self._cancel = cancel
        self._signals = signals

    def run(self) -> None:
        result = import_paths(
            self._paths,
            existing=self._existing,
            include_subfolders=self._include_subfolders,
            progress=self._signals.progress.emit,
            cancel=self._cancel,
        )
        self._signals.done.emit(result)


class PhotoImporter(QObject):
    """Drives an import from the dropped paths to the AddPhotos command.

    ``started``/``progress``/``finished`` drive the progress bar of the status bar; ``cancel``
    stops the scan and adds the photos already read, without asking anything else (§1.1, decision
    0010: with a thousand photos, cancelling must not throw away minutes of work).
    """

    started = Signal()
    progress = Signal(int, int)
    finished = Signal(int)
    """How many photos were added (0 if everything failed or nothing was read before cancelling)."""

    def __init__(
        self, controller: ProjectController, questions: ImportQuestions, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._questions = questions
        self._pass: _Pass | None = None
        self._cancel = CancelToken()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

    @property
    def busy(self) -> bool:
        return self._pass is not None

    def start(self, paths: Sequence[Path], index: int | None = None) -> None:
        """Imports these files and folders; index is the row they are inserted at (None = end)."""
        if self.busy or not paths:
            return
        self._pass = _Pass(tuple(paths), index)
        self._cancel = CancelToken()
        self.started.emit()
        self._scan()

    def cancel(self) -> None:
        self._cancel.cancel()

    def wait(self, milliseconds: int = 30_000) -> bool:
        """Waits for the worker thread (used by the tests and when closing the window)."""
        return self._pool.waitForDone(milliseconds)

    # --- Passes ----------------------------------------------------------------------------------

    def _scan(self) -> None:
        state = self._pass
        if state is None:
            return
        existing: frozenset[Path] = (
            frozenset()
            if state.allow_duplicates
            else frozenset(photo.path for photo in self._controller.project.photos)
        )
        signals = _Signals(self)
        signals.progress.connect(self.progress)
        signals.done.connect(self._on_done)
        self._pool.start(_Scan(state.paths, existing, state.include_subfolders, self._cancel, signals))

    def _on_done(self, result: object) -> None:
        state = self._pass
        if state is None or not isinstance(result, ImportResult):
            return
        if result.cancelled:
            self._add(result, state)
            return
        if result.subfolder_photo_count and not state.asked_subfolders:
            state.asked_subfolders = True
            if self._questions.ask_subfolders(result.subfolder_photo_count):
                state.include_subfolders = True
                self._scan()
                return
        if result.duplicates and not state.asked_duplicates:
            state.asked_duplicates = True
            if self._questions.ask_duplicates(len(result.duplicates)):
                state.allow_duplicates = True
                self._scan()
                return
        self._add(result, state)

    def _add(self, result: ImportResult, state: _Pass) -> None:
        project = self._controller.project
        candidates = sort_candidates(result.candidates)
        photos = tuple(
            photo_from_candidate(candidate, f"p{next(_ids):05d}", project.output_format)
            for candidate in candidates
        )
        if photos:
            self._controller.execute(AddPhotos(photos, state.index))
        if result.failures:
            self._questions.report_failures(result.failures)
        total = len(self._controller.project.photos)
        if photos and total > defaults.MAX_PHOTOS_WITHOUT_WARNING:
            self._questions.warn_many_photos(total)
        self._end(len(photos))

    def _end(self, added: int) -> None:
        self._pass = None
        self.finished.emit(added)
