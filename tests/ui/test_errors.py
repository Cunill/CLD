"""Unexpected errors (B15): logged, and told to the user in Catalan instead of a silent end."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

from passimaker import logs
from passimaker.ui.errors import ErrorReporter
from passimaker.ui.main_window import MainWindow


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    hooks = sys.excepthook, threading.excepthook
    path = logs.setup_logging(tmp_path / "logs")
    assert path is not None
    yield path
    for handler in root.handlers:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)
    sys.excepthook, threading.excepthook = hooks


def logged(path: Path) -> str:
    for handler in logging.getLogger().handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def test_an_error_in_a_slot_is_logged_and_shown(qtbot: QtBot, log_file: Path, window: MainWindow) -> None:
    shown: list[tuple[str, str]] = []
    reporter = ErrorReporter(log_file, show=lambda title, text: shown.append((title, text)))
    logs.install_exception_hooks(reporter.report)

    def broken_slot() -> None:
        raise RuntimeError("fallada provocada")

    QTimer.singleShot(0, broken_slot)
    qtbot.waitUntil(lambda: bool(shown), timeout=5_000)
    assert "fallada provocada" in logged(log_file)
    title, text = shown[0]
    assert title == "Error inesperat"
    assert "error inesperat" in text and "desar el projecte" in text and str(log_file) in text
    assert window.isVisible()  # the program goes on


def test_an_error_in_a_worker_thread_is_shown_on_the_gui_thread(qtbot: QtBot, log_file: Path) -> None:
    on_threads: list[threading.Thread] = []
    reporter = ErrorReporter(log_file, show=lambda _t, _x: on_threads.append(threading.current_thread()))
    logs.install_exception_hooks(reporter.report)

    def fails() -> None:
        raise OSError("lectura del núvol interrompuda")

    worker = threading.Thread(target=fails)
    worker.start()
    worker.join()
    qtbot.waitUntil(lambda: bool(on_threads), timeout=5_000)
    assert on_threads == [threading.main_thread()]
    assert "lectura del núvol interrompuda" in logged(log_file)


def test_errors_while_the_message_is_open_are_not_stacked(qtbot: QtBot, log_file: Path) -> None:
    shown: list[str] = []
    reporter: ErrorReporter

    def show(_title: str, text: str) -> None:
        shown.append(text)
        reporter.report(ValueError("una altra"))  # arrives while the box is open
        qtbot.wait(10)

    reporter = ErrorReporter(log_file, show=show)
    reporter.report(ValueError("primera"))
    qtbot.waitUntil(lambda: reporter.count >= 2, timeout=5_000)
    assert len(shown) == 1


def test_without_a_log_the_message_does_not_name_a_file() -> None:
    reporter = ErrorReporter(None)
    assert "registre" not in reporter.text()
