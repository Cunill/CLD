"""Unexpected errors (B15): written to the log and told to the user, never a silent end.

``passimaker.logs`` writes every uncaught exception to the log, from any thread, and then calls
``ErrorReporter.report``. The report crosses to the GUI thread through a signal and shows one
message in Catalan; errors that arrive while it is open are not stacked on top of it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget


class ErrorReporter(QObject):
    """Tells the user about an error nobody caught; ``show`` is replaced by the tests."""

    _reported = Signal()

    def __init__(
        self,
        log_file: Path | None,
        show: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__()
        self._log_file = log_file
        self._show = show if show is not None else self._message_box
        self._showing = False
        self.window: QWidget | None = None
        """The window the message is shown over; not the parent, so the reporter outlives it."""
        self.count = 0
        """Errors reported since the program started (the tests read it)."""
        self._reported.connect(self._on_reported)

    def report(self, _error: BaseException) -> None:
        """From any thread, after the error has been logged."""
        self._reported.emit()

    def _on_reported(self) -> None:
        self.count += 1
        if self._showing:
            return
        self._showing = True
        try:
            self._show(self.title(), self.text())
        finally:
            self._showing = False

    def title(self) -> str:
        return self.tr("Error inesperat")

    def text(self) -> str:
        first = self.tr(
            "S'ha produït un error inesperat. El programa continua obert, però convé desar el projecte "
            "amb un altre nom i tornar-lo a obrir."
        )
        if self._log_file is None:
            return first
        where = self.tr("Els detalls s'han anotat al registre: {path}").format(path=self._log_file)
        return f"{first}\n\n{where}"

    def _message_box(self, title: str, text: str) -> None:
        QMessageBox.critical(self.window, title, text)
