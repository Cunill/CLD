"""[Exportar vídeo] (§1.9): destination, progress dialog, cancel, and what to do with the video.

The export runs ``passimaker.export.export_project`` in a worker thread; its progress arrives
through a queued signal. The dialog is window-modal (§1.9: no editing while exporting) but opened
with ``open()``, not ``exec()``, so the GUI thread keeps running and the tests can drive it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from passimaker.common import CancelToken
from passimaker.export import ERROR_FAILED, ExportResult, ExportStatus, export_project, missing_files
from passimaker.i18n import message
from passimaker.model import Project
from passimaker.ui.formatting import clock, megabytes

VIDEO_EXTENSION = ".mp4"
PROGRESS_STEPS = 1000
"""Resolution of the progress bar (0.1 %)."""

type Exporter = Callable[..., ExportResult]
type UrlOpener = Callable[[QUrl], bool]


def suggested_video_path(name: str, fallback: str) -> Path:
    """§1.9: the name of the project in the Videos folder."""
    folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
    base = Path(folder) if folder else Path.home()
    return base / f"{name or fallback}{VIDEO_EXTENSION}"


class ExportQuestions(Protocol):
    def choose_export_path(self, suggested: Path) -> Path | None:
        """The save dialog of §1.9; it asks before replacing an existing file."""
        ...

    def report_missing_files(self, paths: Sequence[Path]) -> None:
        """§1.9: files that are not found; nothing is exported."""
        ...


class ExportJob(QObject):
    """export_project in a worker thread; its callbacks become signals on the GUI thread."""

    progress = Signal(float, object)
    """fraction 0-1 and the remaining seconds (or None while unknown)."""
    finished = Signal(object)
    """The ExportResult."""

    def __init__(
        self, project: Project, dest: Path, exporter: Exporter, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.dest = dest
        self._exporter = exporter
        self._cancel = CancelToken()
        self._thread: threading.Thread | None = None
        self.result: ExportResult | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="passimaker-export", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.cancel()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout_s: float | None = None) -> bool:
        if self._thread is not None:
            self._thread.join(timeout_s)
        return not self.running

    def _run(self) -> None:
        try:
            result = self._exporter(self.project, self.dest, progress=self._report, cancel=self._cancel)
        except Exception:  # export_project returns its errors; this is the last guard
            result = ExportResult(ExportStatus.ERROR, ERROR_FAILED, 0.0, 0)
        self.result = result
        self.finished.emit(result)

    def _report(self, fraction: float, remaining_s: float | None) -> None:
        self.progress.emit(fraction, remaining_s)


class ExportDialog(QDialog):
    """Bar, percentage, remaining time and [Cancel·lar]; then [Obrir el vídeo] / [Mostrar a la carpeta]."""

    def __init__(self, job: ExportJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.opener: UrlOpener = QDesktopServices.openUrl
        self.setWindowTitle(self.tr("Exportar vídeo"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(420)

        self.title_label = QLabel(self.tr("Exportant {name}…").format(name=job.dest.name))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, PROGRESS_STEPS)
        self.progress_bar.setTextVisible(False)
        self.percent_label = QLabel(self.tr("{percent} %").format(percent=0))
        self.remaining_label = QLabel(self.tr("Calculant el temps restant…"))
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)

        self.cancel_button = QPushButton(self.tr("Cancel·lar"))
        self.cancel_button.clicked.connect(self.cancel)
        self.open_video_button = QPushButton(self.tr("Obrir el vídeo"))
        self.open_video_button.clicked.connect(self.open_video)
        self.show_folder_button = QPushButton(self.tr("Mostrar a la carpeta"))
        self.show_folder_button.clicked.connect(self.show_folder)
        self.close_button = QPushButton(self.tr("Tancar"))
        self.close_button.clicked.connect(self.accept)
        for button in (self.open_video_button, self.show_folder_button, self.close_button):
            button.setVisible(False)

        figures = QHBoxLayout()
        figures.addWidget(self.percent_label)
        figures.addStretch(1)
        figures.addWidget(self.remaining_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for button in (
            self.open_video_button,
            self.show_folder_button,
            self.close_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(figures)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)

        job.progress.connect(self._on_progress)
        job.finished.connect(self._on_finished)

    def start(self) -> None:
        self.open()
        self.job.start()

    def cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.remaining_label.setText(self.tr("Cancel·lant…"))
        self.job.cancel()

    def open_video(self) -> None:
        self.opener(QUrl.fromLocalFile(str(self.job.dest)))

    def show_folder(self) -> None:
        self.opener(QUrl.fromLocalFile(str(self.job.dest.parent)))

    # --- Progress --------------------------------------------------------------------------------

    def _on_progress(self, fraction: float, remaining_s: object) -> None:
        self.progress_bar.setValue(round(fraction * PROGRESS_STEPS))
        self.percent_label.setText(self.tr("{percent} %").format(percent=int(fraction * 100)))
        if not self.cancel_button.isEnabled():
            return
        if isinstance(remaining_s, (int, float)):
            self.remaining_label.setText(self.tr("Queden {time}").format(time=clock(remaining_s)))

    def _on_finished(self, result: object) -> None:
        if not isinstance(result, ExportResult):
            return
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)
        self.remaining_label.setText("")
        if result.status is ExportStatus.DONE:
            self.progress_bar.setValue(PROGRESS_STEPS)
            self.percent_label.setText(self.tr("{percent} %").format(percent=100))
            self.title_label.setText(
                self.tr("Vídeo desat ({duration}, {size})").format(
                    duration=clock(result.duration_s), size=megabytes(result.size_bytes)
                )
            )
            self.open_video_button.setVisible(True)
            self.show_folder_button.setVisible(True)
            self.open_video_button.setDefault(True)
            return
        if result.status is ExportStatus.CANCELLED:
            self.title_label.setText(self.tr("S'ha cancel·lat l'exportació. No s'ha desat cap fitxer."))
        else:
            self.title_label.setText(self.tr("No s'ha pogut exportar el vídeo."))
            self.message_label.setText(message(result.reason_key or ERROR_FAILED))
            self.message_label.setVisible(True)
        self.close_button.setDefault(True)

    # --- Closing ---------------------------------------------------------------------------------

    def reject(self) -> None:
        """Escape or the close box while exporting cancel the export instead of hiding it."""
        if self.job.running:
            self.cancel()
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt)
        if self.job.running:
            self.cancel()
            event.ignore()
            return
        super().closeEvent(event)


class VideoExport(QObject):
    """The whole of [Exportar vídeo]: checks, destination and the progress dialog."""

    finished = Signal(object)
    """The ExportResult, once the dialog has it."""

    def __init__(self, questions: ExportQuestions, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._questions = questions
        self._parent = parent
        self.exporter: Exporter = export_project
        self.dialog: ExportDialog | None = None

    @property
    def running(self) -> bool:
        return self.dialog is not None and self.dialog.job.running

    def start(self, project: Project, name: str) -> ExportDialog | None:
        """Asks where to save and starts; None if there is nothing to export or the user cancelled."""
        if not project.photos or self.running:
            return None
        missing = missing_files(project)
        if missing:
            self._questions.report_missing_files(missing)
            return None
        dest = self._questions.choose_export_path(suggested_video_path(name, self.tr("Passi")))
        if dest is None:
            return None
        if dest.suffix.lower() != VIDEO_EXTENSION:
            dest = dest.with_name(dest.name + VIDEO_EXTENSION)
        return self.export_to(project, dest)

    def export_to(self, project: Project, dest: Path) -> ExportDialog:
        job = ExportJob(project, dest, self.exporter, self)
        job.finished.connect(self.finished)
        self.dialog = ExportDialog(job, self._parent)
        self.dialog.start()
        return self.dialog

    def cancel_and_wait(self, timeout_s: float = 5.0) -> None:
        if self.dialog is not None and self.dialog.job.running:
            self.dialog.job.cancel()
            self.dialog.job.wait(timeout_s)
