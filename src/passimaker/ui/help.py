"""The Ajuda menu (block B16): a one-page user guide, the keyboard shortcuts and "Quant a".

Both windows are modeless: they can stay open next to the main window while the user follows
the guide, and the tests can open them without a modal loop. The guide is written here, inside
``tr()``, so that it travels with the program (no extra file to package) and can be translated
like every other text (rule 8).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from passimaker import __version__

GUIDE_SIZE = (620, 680)
ABOUT_SIZE = (460, 420)


@dataclass(frozen=True, slots=True)
class Shortcut:
    keys: QKeySequence
    description: str


def shortcuts() -> list[Shortcut]:
    """Every keyboard shortcut of the window, in the order of the guide (a test checks the list)."""
    rows = [
        ("Ctrl+O", QCoreApplication.translate("Help", "Obrir un projecte")),
        ("Ctrl+S", QCoreApplication.translate("Help", "Desar el projecte")),
        ("Ctrl+Shift+S", QCoreApplication.translate("Help", "Desar el projecte amb un altre nom")),
        ("Ctrl+E", QCoreApplication.translate("Help", "Exportar el vídeo")),
        ("Ctrl+Z", QCoreApplication.translate("Help", "Desfer")),
        ("Ctrl+Y", QCoreApplication.translate("Help", "Refer (també Ctrl+Maj+Z)")),
        ("Space", QCoreApplication.translate("Help", "Reproduir o aturar la previsualització")),
        ("Left", QCoreApplication.translate("Help", "Foto anterior a la previsualització")),
        ("Right", QCoreApplication.translate("Help", "Foto següent a la previsualització")),
        ("Ctrl+A", QCoreApplication.translate("Help", "Seleccionar totes les fotos")),
        ("Del", QCoreApplication.translate("Help", "Eliminar les fotos seleccionades")),
        ("Ctrl+D", QCoreApplication.translate("Help", "Duplicar les fotos seleccionades")),
        ("Ctrl+Left", QCoreApplication.translate("Help", "Moure les fotos seleccionades a l'esquerra")),
        ("Ctrl+Right", QCoreApplication.translate("Help", "Moure les fotos seleccionades a la dreta")),
        ("Ctrl+R", QCoreApplication.translate("Help", "Girar les fotos seleccionades a la dreta")),
        ("Ctrl+Shift+R", QCoreApplication.translate("Help", "Girar les fotos seleccionades a l'esquerra")),
        ("F1", QCoreApplication.translate("Help", "Aquesta guia")),
        ("Ctrl+Q", QCoreApplication.translate("Help", "Sortir del programa")),
    ]
    return [Shortcut(QKeySequence(keys), description) for keys, description in rows]


def _key_text(keys: QKeySequence) -> str:
    return keys.toString(QKeySequence.SequenceFormat.NativeText)


def shortcuts_html(rows: Sequence[Shortcut]) -> str:
    lines = "".join(
        f"<tr><td style='padding-right:16px'><b>{_key_text(row.keys)}</b></td><td>{row.description}</td></tr>"
        for row in rows
    )
    return f"<table cellspacing='2'>{lines}</table>"


def guide_html() -> str:
    """The one-page guide: the three steps of §1.0, the usual adjustments and the shortcuts."""
    parts = [
        QCoreApplication.translate("Help", "<h2>Com es fa un passi</h2>"),
        QCoreApplication.translate(
            "Help",
            "<p>PassiMaker converteix una carpeta de fotos en un vídeo amb moviment suau, foses entre les "
            "fotos i música. Tot té valors pensats perquè quedi bé sense tocar res: n'hi ha prou amb tres "
            "passos.</p>",
        ),
        QCoreApplication.translate("Help", "<h3>1. Fotos</h3>"),
        QCoreApplication.translate(
            "Help",
            "<p>Arrossega les fotos o tota la carpeta a la finestra, o fes clic a <b>[+ Fotos]</b>. "
            "S'ordenen per la data en què es van fer. Per canviar-ne l'ordre, arrossega-les al "
            "storyboard; per treure'n una, selecciona-la i prem <b>Supr</b>. Admet JPG, PNG, HEIC i altres "
            "formats habituals; els fitxers RAW de càmera no.</p>",
        ),
        QCoreApplication.translate("Help", "<h3>2. Música</h3>"),
        QCoreApplication.translate(
            "Help",
            "<p>Fes clic a <b>[+ Música]</b> o arrossega les cançons a la franja de música. La barra "
            "d'estat avisa si la música i les fotos no duren el mateix: <b>[Ajustar a la música]</b> "
            "canvia la durada de les fotos perquè el passi acabi alhora que la música.</p>",
        ),
        QCoreApplication.translate("Help", "<h3>3. Exportar</h3>"),
        QCoreApplication.translate(
            "Help",
            "<p>Mira el resultat amb <b>▶</b> (o la barra espaiadora) i fes clic a <b>[Exportar vídeo]</b>. "
            "El vídeo és un MP4 Full HD que es veu a qualsevol televisor, mòbil o ordinador. Tria "
            "<b>Format vertical</b> a la barra d'eines si el vídeo és per veure'l al mòbil.</p>",
        ),
        QCoreApplication.translate("Help", "<h3>Si vols ajustar alguna cosa</h3>"),
        QCoreApplication.translate(
            "Help",
            "<ul>"
            "<li><b>Tot el passi</b>: pestanya <i>Projecte</i> (durada de les fotos, fosa, intensitat del "
            "moviment). Les opcions menys habituals són a <i>Avançat</i>.</li>"
            "<li><b>Una foto</b>: selecciona-la i fes servir la pestanya <i>Foto</i> (durada, moviment, "
            "encaix i gir). Si un moviment no t'agrada, <b>🎲 Tornar a sortejar</b>.</li>"
            "<li><b>Una cançó</b>: selecciona-la a la franja de música i fes servir la pestanya "
            "<i>Cançó</i> (retall, foses i volum). <b>▶ Escoltar el tros</b> la fa sonar tal com "
            "quedarà.</li>"
            "<li>Tot es pot desfer amb <b>Ctrl+Z</b>.</li>"
            "</ul>",
        ),
        QCoreApplication.translate("Help", "<h3>Desar</h3>"),
        QCoreApplication.translate(
            "Help",
            "<p>Desa el projecte (<b>Ctrl+S</b>) per continuar-lo un altre dia. El projecte és un fitxer "
            "<b>.pmk</b> que només guarda on són les fotos i les cançons: no les copia ni les modifica "
            "mai. Si mous les fotos, el programa et deixarà cercar-les en una carpeta. Si el programa es "
            "tanca de cop, en tornar-lo a obrir t'oferirà recuperar el projecte.</p>",
        ),
        QCoreApplication.translate("Help", "<h3>Dreceres de teclat</h3>"),
        shortcuts_html(shortcuts()),
        QCoreApplication.translate("Help", "<h3>Imprevistos</h3>"),
        QCoreApplication.translate(
            "Help",
            "<p>Si alguna cosa no funciona o es queda encallat, pitja tecles aleatòriament i fes cercles amb "
            "el ratolí. I si tot i així no s'arregla, aixeca't i fes tres voltes a la cadira.</p>",
        ),
    ]
    return "".join(parts)


def about_html(log_folder: Path | None) -> str:
    parts = [
        QCoreApplication.translate("Help", "<h2>PassiMaker {version}</h2>").format(version=__version__),
        QCoreApplication.translate(
            "Help",
            "<p>Passis de fotos amb moviment, foses i música, exportats a vídeo MP4 Full HD. Funciona sense "
            "connexió i no modifica mai les fotos ni les cançons originals.</p>",
        ),
        QCoreApplication.translate(
            "Help",
            "<p>Fet amb Python, Qt for Python (PySide6, llicència LGPL), FFmpeg (llicència a la carpeta "
            "<i>bin\\llicencies</i>), NumPy, OpenCV, Pillow i pillow-heif.</p>",
        ),
    ]
    if log_folder is not None:
        parts.append(
            QCoreApplication.translate("Help", "<p>Registre d'errors: {path}</p>").format(path=log_folder)
        )
    return "".join(parts)


class _TextWindow(QDialog):
    """A modeless window with rich text and a [Tancar] button."""

    def __init__(self, title: str, html: str, size: tuple[int, int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(*size)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setHtml(html)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.browser)
        layout.addWidget(buttons)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)


class HelpWindows:
    """Opens the guide and "Quant a"; a second request brings the open window to the front."""

    def __init__(self, parent: QWidget, log_folder: Path | None = None) -> None:
        self._parent = parent
        self._log_folder = log_folder
        self.guide: _TextWindow | None = None
        self.about: _TextWindow | None = None

    def show_guide(self) -> QDialog:
        if self.guide is None:
            self.guide = _TextWindow(
                QCoreApplication.translate("Help", "Guia de PassiMaker"),
                guide_html(),
                GUIDE_SIZE,
                self._parent,
            )
        return self._raise(self.guide)

    def show_about(self) -> QDialog:
        if self.about is None:
            self.about = _TextWindow(
                QCoreApplication.translate("Help", "Quant a PassiMaker"),
                about_html(self._log_folder),
                ABOUT_SIZE,
                self._parent,
            )
        return self._raise(self.about)

    def close(self) -> None:
        for window in (self.guide, self.about):
            if window is not None:
                window.close()

    @staticmethod
    def _raise(window: QDialog) -> QDialog:
        window.show()
        window.raise_()
        window.activateWindow()
        return window
