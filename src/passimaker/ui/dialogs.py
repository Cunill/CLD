"""The questions, warnings and file choosers of §1.1, §1.2, §1.7, §1.9 and §1.10, as dialogs.

They are behind a protocol so that the window can be driven by the tests without a screen: the
window never opens a dialog itself, it asks this object, and the tests replace it by one that
answers straight away (a modal dialog would stop them for ever).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

from PySide6.QtWidgets import QAbstractButton, QFileDialog, QMessageBox, QWidget

from passimaker.i18n import message
from passimaker.importer import SUPPORTED_EXTENSIONS, FailedFile
from passimaker.projectio import EXTENSION
from passimaker.ui.duration_status import FitCheck, FitProblem
from passimaker.ui.export_dialog import ExportQuestions
from passimaker.ui.formatting import duration
from passimaker.ui.importing import ImportQuestions
from passimaker.ui.music_strip import AUDIO_EXTENSIONS, FailedSong, SongQuestions
from passimaker.ui.project_files import FileQuestions, SaveAnswer

MAX_LISTED_FAILURES = 20
"""Files listed in the details of "no s'han pogut afegir"; the rest are counted."""


class WindowQuestions(ImportQuestions, SongQuestions, ExportQuestions, FileQuestions, Protocol):
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

    def choose_music(self) -> list[Path]:
        """[+ Música]: the audio files chosen, in order, or an empty list (§1.7)."""
        ...

    def confirm_fit(self, check: FitCheck) -> bool:
        """§1.7: the photos would end outside 1-3 s. True is [Aplicar igualment]."""
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
            (
                self.tr("Vols incloure també les subcarpetes (1 foto més)?")
                if count == 1
                else self.tr("Vols incloure també les subcarpetes ({n} fotos més)?").format(n=count)
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return answer == QMessageBox.StandardButton.Yes

    def ask_duplicates(self, count: int) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Fotos repetides"),
            (
                self.tr("1 foto ja hi és. La vols afegir igualment?")
                if count == 1
                else self.tr("{n} fotos ja hi són. Les vols afegir igualment?").format(n=count)
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def report_failures(self, failures: Sequence[FailedFile]) -> None:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Importació"))
        box.setText(
            self.tr("1 fitxer no s'ha pogut afegir.")
            if len(failures) == 1
            else self.tr("{n} fitxers no s'han pogut afegir.").format(n=len(failures))
        )
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

    def choose_download_folder(self, suggested: Path) -> Path | None:
        """[Descarrega en MP3] (§1.7 bis): where the songs from YouTube go, starting at `suggested`."""
        folder = QFileDialog.getExistingDirectory(
            self.parentWidget(), self.tr("Tria on vols desar les cançons"), str(suggested)
        )
        return Path(folder) if folder else None

    def choose_music(self) -> list[Path]:
        patterns = " ".join(f"*{extension}" for extension in sorted(AUDIO_EXTENSIONS))
        chosen, _ = QFileDialog.getOpenFileNames(
            self.parentWidget(), self.tr("Tria la música"), "", self.tr("Música") + f" ({patterns})"
        )
        return [Path(path) for path in chosen]

    def report_song_failures(self, failures: Sequence[FailedSong]) -> None:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Música"))
        box.setText(
            self.tr("1 cançó no s'ha pogut afegir.")
            if len(failures) == 1
            else self.tr("{n} cançons no s'han pogut afegir.").format(n=len(failures))
        )
        box.setDetailedText(
            "\n".join(f"{failure.path.name}: {message(failure.message_key)}" for failure in failures)
        )
        box.exec()

    def confirm_fit(self, check: FitCheck) -> bool:
        return self._answer(self.fit_box(check)) is QMessageBox.ButtonRole.AcceptRole

    def fit_box(self, check: FitCheck) -> QMessageBox:
        if check.problem is FitProblem.TOO_MANY_PHOTOS:
            text = self.tr(
                "Hi ha massa fotos per a aquesta música: cada foto duraria {seconds}. "
                "Afegeix música o treu fotos."
            ).format(seconds=duration(check.seconds_per_photo))
        else:
            text = self.tr("La música és massa llarga per a aquestes fotos: afegeix-ne o retalla la música.")
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Ajustar a la música"))
        box.setText(text)
        box.addButton(self.tr("Aplicar igualment"), QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(self.tr("Cancel·lar"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        return box

    def choose_export_path(self, suggested: Path) -> Path | None:
        chosen, _ = QFileDialog.getSaveFileName(
            self.parentWidget(), self.tr("Exportar vídeo"), str(suggested), self.tr("Vídeo MP4") + " (*.mp4)"
        )
        return Path(chosen) if chosen else None

    def report_missing_files(self, paths: Sequence[Path]) -> None:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Exportar vídeo"))
        box.setText(
            self.tr("No es pot exportar: no es troba 1 fitxer.")
            if len(paths) == 1
            else self.tr("No es pot exportar: no es troben {n} fitxers.").format(n=len(paths))
        )
        box.setDetailedText(path_list(paths))
        box.exec()

    def choose_project_to_open(self) -> Path | None:
        chosen, _ = QFileDialog.getOpenFileName(
            self.parentWidget(), self.tr("Obrir un projecte"), "", self.tr("Projectes") + f" (*{EXTENSION})"
        )
        return Path(chosen) if chosen else None

    def choose_project_save_path(self, suggested: Path) -> Path | None:
        chosen, _ = QFileDialog.getSaveFileName(
            self.parentWidget(),
            self.tr("Desar el projecte"),
            str(suggested),
            self.tr("Projectes") + f" (*{EXTENSION})",
        )
        return Path(chosen) if chosen else None

    def ask_save_changes(self, name: str) -> SaveAnswer:
        role = self._answer(self.save_changes_box(name))
        if role is QMessageBox.ButtonRole.AcceptRole:
            return SaveAnswer.SAVE
        if role is QMessageBox.ButtonRole.DestructiveRole:
            return SaveAnswer.DISCARD
        return SaveAnswer.CANCEL

    def save_changes_box(self, name: str) -> QMessageBox:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Canvis sense desar"))
        box.setText(self.tr("Vols desar els canvis de «{name}»?").format(name=name))
        save = box.addButton(self.tr("Desar"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr("No desar"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(self.tr("Cancel·lar"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        return box

    def offer_recovery(self) -> bool:
        return self._answer(self.recovery_box()) is QMessageBox.ButtonRole.AcceptRole

    def recovery_box(self) -> QMessageBox:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Recuperar el projecte"))
        box.setText(
            self.tr("El programa es va tancar sense desar el projecte. Vols recuperar l'última còpia?")
        )
        recover = box.addButton(self.tr("Recuperar"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr("Descartar"), QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(recover)
        return box

    def ask_relink(self, count: int) -> Path | None:
        if self._answer(self.relink_box(count)) is QMessageBox.ButtonRole.AcceptRole:
            return self.choose_folder()
        return None

    def relink_box(self, count: int) -> QMessageBox:
        box = QMessageBox(self.parentWidget())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Fitxers que no es troben"))
        box.setText(
            self.tr("No es troba 1 fitxer.")
            if count == 1
            else self.tr("No es troben {n} fitxers.").format(n=count)
        )
        search = box.addButton(self.tr("Cercar en una carpeta…"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr("Ara no"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(search)
        return box

    def report_relinked(self, found: int, still_missing: int) -> None:
        if still_missing:
            if found == 0:
                first = self.tr("No s'ha trobat cap fitxer.")
            elif found == 1:
                first = self.tr("S'ha trobat 1 fitxer.")
            else:
                first = self.tr("S'han trobat {found} fitxers.").format(found=found)
            rest = (
                self.tr("Encara en falta 1.")
                if still_missing == 1
                else self.tr("Encara en falten {missing}.").format(missing=still_missing)
            )
            text = f"{first} {rest}"
        elif found == 1:
            text = self.tr("S'ha trobat el fitxer.")
        else:
            text = self.tr("S'han trobat tots els fitxers ({found}).").format(found=found)
        QMessageBox.information(self.parentWidget(), self.tr("Fitxers que no es troben"), text)

    def show_error(self, text: str) -> None:
        QMessageBox.critical(self.parentWidget(), self.tr("PassiMaker"), text)

    @staticmethod
    def _answer(box: QMessageBox) -> QMessageBox.ButtonRole:
        """Shows a question built by one of the *_box methods (the screenshots show them too)."""
        box.exec()
        clicked = cast(QAbstractButton | None, box.clickedButton())  # None after Escape without a cancel
        return box.buttonRole(clicked) if clicked is not None else QMessageBox.ButtonRole.RejectRole


def path_list(paths: Sequence[Path]) -> str:
    """One path per line, the first MAX_LISTED_FAILURES (§1.9: the list of missing files)."""
    lines = [str(path) for path in paths[:MAX_LISTED_FAILURES]]
    if len(paths) > MAX_LISTED_FAILURES:
        lines.append(f"… ({len(paths) - MAX_LISTED_FAILURES})")
    return "\n".join(lines)


def failure_details(failures: Sequence[FailedFile]) -> str:
    """One line per file with its Catalan reason ([Veure quins] of §1.1)."""
    lines = [
        f"{failure.path.name}: {message(f'import.{failure.reason.value}')}"
        for failure in failures[:MAX_LISTED_FAILURES]
    ]
    if len(failures) > MAX_LISTED_FAILURES:
        lines.append(f"… ({len(failures) - MAX_LISTED_FAILURES})")
    return "\n".join(lines)
