"""Application entry point (`passimaker`): builds the services and opens the main window."""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from passimaker.export import cache_root
from passimaker.images import CachedImageSource
from passimaker.logs import install_exception_hooks, setup_logging
from passimaker.model import ProjectController
from passimaker.recorder import remove_leftovers
from passimaker.thumbs import ThumbnailService
from passimaker.ui.errors import ErrorReporter
from passimaker.ui.main_window import MainWindow
from passimaker.ui.project_files import APPLICATION, ORGANISATION
from passimaker.ui.translations import install

ICON_FILE = Path(__file__).with_name("app_icon.png")
"""Made by packaging/generar_icona.py; PassiMaker.spec copies it next to this module."""


def app_icon() -> QIcon:
    """The window and taskbar icon (a null icon if the file is missing: the program still starts)."""
    return QIcon(str(ICON_FILE))


def remove_recording_leftovers() -> threading.Thread:
    """The temporary WAVs of a recording cut short by a crash are deleted, never recovered (G1).

    In a thread of its own: listing the temporary folder may take a moment (rule 6).
    """
    thread = threading.Thread(
        target=lambda: remove_leftovers(Path(tempfile.gettempdir())), name="passimaker-leftovers", daemon=True
    )
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    """Starts the GUI. Optional argument: a .pmk file to open; without it, the recovery copy is offered
    if the program did not close cleanly last time (§1.10)."""
    args = sys.argv[1:] if argv is None else argv
    log_file = setup_logging()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName(ORGANISATION)
    app.setApplicationName(APPLICATION)
    app.setWindowIcon(app_icon())
    install(app)
    reporter = ErrorReporter(log_file)
    install_exception_hooks(reporter.report)
    remove_recording_leftovers()

    images = CachedImageSource()
    thumbnails = ThumbnailService(cache_root() / "thumbs", CachedImageSource())
    window = MainWindow(ProjectController(), thumbnails, images)
    reporter.window = window
    window.show()
    window.files.startup(Path(args[0]) if args else None)
    try:
        return app.exec()
    finally:
        thumbnails.close()
