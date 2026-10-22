"""Application entry point (`passimaker`): builds the services and opens the main window."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from passimaker.common import PassiMakerError
from passimaker.export import cache_root
from passimaker.i18n import message
from passimaker.images import CachedImageSource
from passimaker.model import Project, ProjectController
from passimaker.projectio import open_project
from passimaker.thumbs import ThumbnailService
from passimaker.ui.main_window import MainWindow
from passimaker.ui.translations import install

ORGANISATION = "PassiMaker"
APPLICATION = "PassiMaker"


def main(argv: list[str] | None = None) -> int:
    """Starts the GUI. Optional argument: a .pmk file to open."""
    args = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    app = QApplication(sys.argv[:1])
    app.setOrganizationName(ORGANISATION)
    app.setApplicationName(APPLICATION)
    install(app)

    project, error = _open(Path(args[0])) if args else (Project(), None)
    images = CachedImageSource()
    thumbnails = ThumbnailService(cache_root() / "thumbs", CachedImageSource())
    window = MainWindow(ProjectController(project), thumbnails, images)
    window.show()
    if error is not None:
        QMessageBox.critical(window, window.tr("PassiMaker"), error)
    try:
        return app.exec()
    finally:
        thumbnails.close()


def _open(path: Path) -> tuple[Project, str | None]:
    """The project of the given file, or an empty one and the message to show."""
    try:
        return open_project(path).project, None
    except PassiMakerError as failure:
        return Project(), message(failure.message_key)
