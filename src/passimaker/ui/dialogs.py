"""The questions, warnings and file choosers of §1.1 and §1.2, as dialogs.

They are behind a protocol so that the window can be driven by the tests without a screen: the
window never opens a dialog itself, it asks this object, and the tests replace it by one that
answers straight away (a modal dialog would stop them for ever).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from passimaker.i18n import message
from passimaker.importer import SUPPORTED_EXTENSIONS, FailedFile
from passimaker.ui.importing import ImportQuestions

MAX_LISTED_FAILURES = 20
"""Files listed in the details of "no s'han pogut afegir"; the rest are counted."""


class WindowQuestions(ImportQuestions, Protocol):
    """Everything the window asks the user."""

    def confirm_delete(self, count: int) -> bool:
        """§1.2 and decision 0007: five photos or more need a confirmation, even with undo."""
        ...

    def choose_photos(self) -> list[Path]:
        """[Tria fotos…]: the files chosen, or an empty list (§1.1)."""
        ...

    def choose_folder(self) -> Path | None:
        """ "Afegir una carpeta…": the folder chosen, or None."""
        ...


class DialogQuestions(QWidget):
    """The real questions, as modal dialogs over the window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)

    def ask_subfolders(self, count: int) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Subcarpetes"),
            self.tr("Vols incloure també les subcarpetes ({n} fotos més)?").format(n=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return answer == QMessageBox.StandardButton.Yes

    def ask_duplicates(self, count: int) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Fotos repetides"),
            self.tr("{n} fotos ja hi són. Les vols afegir igualment?").format(n=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def report_failures(self, failures: Sequence[FailedFile]) -> None:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Importació"))
        box.setText(self.tr("{n} fitxers no s'han pogut afegir.").format(n=len(failures)))
        box.setDetailedText(failure_details(failures))
        box.exec()

    def warn_many_photos(self, count: int) -> None:
        QMessageBox.information(
            self.parentWidget(),
            self.tr("Moltes fotos"),
            self.tr("Més de {n} fotos: el programa pot anar més lent.").format(n=count),
        )

    def confirm_delete(self, count: int) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Eliminar fotos"),
            self.tr("Vols eliminar {n} fotos del passi?").format(n=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def choose_photos(self) -> list[Path]:
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS))
        chosen, _ = QFileDialog.getOpenFileNames(
            self.parentWidget(), self.tr("Tria fotos"), "", self.tr("Fotos") + f" ({patterns})"
        )
        return [Path(path) for path in chosen]

    def choose_folder(self) -> Path | None:
        folder = QFileDialog.getExistingDirectory(self.parentWidget(), self.tr("Tria una carpeta"))
        return Path(folder) if folder else None


def failure_details(failures: Sequence[FailedFile]) -> str:
    """One line per file with its Catalan reason ([Veure quins] of §1.1)."""
    lines = [
        f"{failure.path.name}: {message(f'import.{failure.reason.value}')}"
        for failure in failures[:MAX_LISTED_FAILURES]
    ]
    if len(failures) > MAX_LISTED_FAILURES:
        lines.append(f"… ({len(failures) - MAX_LISTED_FAILURES})")
    return "\n".join(lines)
