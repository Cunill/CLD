"""Base of the translations (rule 8).

Every visible text is written in Catalan inside ``tr()``, so the program is already in Catalan
with no catalogue at all. This module installs two optional catalogues on top:

- Qt's own (``qtbase_ca``), which translates the buttons of the standard dialogs ("Yes", "No",
  "Cancel"…), shipped with PySide6;
- ``ca.qm`` next to this file, if a future block generates one (``pyside6-lupdate`` collects the
  ``tr()`` calls, ``pyside6-lrelease`` compiles them).

Both are optional: ``install`` says which ones it managed to load, and the program works without.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

LANGUAGE = "ca"
CATALOGUE = Path(__file__).resolve().parent / f"{LANGUAGE}.qm"

_installed: list[QTranslator] = []
"""Qt keeps only a borrowed reference to a translator: they are held here so they stay alive."""


def install(app: QCoreApplication) -> list[str]:
    """Installs the available catalogues; returns the names of the ones that were loaded."""
    QLocale.setDefault(QLocale(LANGUAGE))
    loaded: list[str] = []
    qt_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name, directory in (("qtbase", qt_path), (LANGUAGE, str(CATALOGUE.parent))):
        translator = QTranslator()
        source = f"{name}_{LANGUAGE}" if name != LANGUAGE else name
        if translator.load(source, directory) and app.installTranslator(translator):
            _installed.append(translator)
            loaded.append(source)
    return loaded
