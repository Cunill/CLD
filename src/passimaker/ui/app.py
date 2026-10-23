"""Application entry point (`passimaker`): builds the services and opens the main window."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from passimaker.export import cache_root
from passimaker.images import CachedImageSource
from passimaker.model import ProjectController
from passimaker.thumbs import ThumbnailService
from passimaker.ui.main_window import MainWindow
from passimaker.ui.project_files import APPLICATION, ORGANISATION
from passimaker.ui.translations import install


def main(argv: list[str] | None = None) -> int:
    """Starts the GUI. Optional argument: a .pmk file to open; without it, the recovery copy is offered
    if the program did not close cleanly last time (§1.10)."""
    args = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    app = QApplication(sys.argv[:1])
    app.setOrganizationName(ORGANISATION)
    app.setApplicationName(APPLICATION)
    install(app)

    images = CachedImageSource()
    thumbnails = ThumbnailService(cache_root() / "thumbs", CachedImageSource())
    window = MainWindow(ProjectController(), thumbnails, images)
    window.show()
    window.files.startup(Path(args[0]) if args else None)
    try:
        return app.exec()
    finally:
        thumbnails.close()
