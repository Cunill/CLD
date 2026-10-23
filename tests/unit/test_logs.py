"""The error log (B15): where it goes, how it renews itself and what reaches it."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from passimaker import logs


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """setup_logging changes process-wide state: the root logger and the exception hooks."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    main_hook, thread_hook = sys.excepthook, threading.excepthook
    yield
    for handler in root.handlers:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)
    sys.excepthook, threading.excepthook = main_hook, thread_hook


def flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_the_default_folder_is_under_local_app_data_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(logs.LOG_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(Path("C:/Users/Anna/AppData/Local")))
    assert logs.log_dir() == Path("C:/Users/Anna/AppData/Local") / "PassiMaker" / "logs"


def test_the_variable_overrides_the_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(logs.LOG_ENV_VAR, str(tmp_path / "registre"))
    assert logs.log_dir() == tmp_path / "registre"


def test_warnings_of_any_module_reach_the_file(tmp_path: Path) -> None:
    path = logs.setup_logging(tmp_path / "logs")
    assert path is not None
    assert path == tmp_path / "logs" / logs.LOG_FILE_NAME
    logging.getLogger("passimaker.thumbs.disk").warning("Cannot write cache file %s", "x.jpg")
    flush()
    text = path.read_text(encoding="utf-8")
    assert "PassiMaker" in text  # the first line says which version wrote it
    assert "WARNING" in text and "passimaker.thumbs.disk" in text and "x.jpg" in text


def test_the_log_renews_itself_with_five_files_of_five_megabytes(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    logs.setup_logging(folder)
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 4
    handler.maxBytes = 2_000  # the same rule, quicker to fill
    line = "x" * 200
    for _ in range(200):
        logging.getLogger("passimaker").warning(line)
    flush()
    files = sorted(p.name for p in folder.iterdir())
    assert files == [
        "passimaker.log",
        "passimaker.log.1",
        "passimaker.log.2",
        "passimaker.log.3",
        "passimaker.log.4",
    ]
    assert all(p.stat().st_size <= 2_000 + 400 for p in folder.iterdir())


def test_calling_it_again_does_not_duplicate_the_lines(tmp_path: Path) -> None:
    logs.setup_logging(tmp_path / "a")
    path = logs.setup_logging(tmp_path / "b")
    assert path is not None
    files = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    assert len(files) == 1
    logging.getLogger("passimaker").warning("una vegada")
    flush()
    assert path.read_text(encoding="utf-8").count("una vegada") == 1


def test_a_folder_that_cannot_be_created_does_not_stop_the_program(tmp_path: Path) -> None:
    blocker = tmp_path / "fitxer"
    blocker.write_text("no és una carpeta", encoding="utf-8")
    assert logs.setup_logging(blocker / "logs") is None
    logging.getLogger("passimaker").warning("sense registre")  # no exception


def test_an_uncaught_exception_is_logged_and_reported(tmp_path: Path) -> None:
    reported: list[BaseException] = []
    path = logs.setup_logging(tmp_path, on_error=reported.append)
    assert path is not None
    error = ValueError("res no l'ha capturada")
    try:
        raise error
    except ValueError:
        sys.excepthook(*sys.exc_info())  # pyright: ignore[reportArgumentType]
    flush()
    text = path.read_text(encoding="utf-8")
    assert "CRITICAL" in text and "res no l'ha capturada" in text and "Traceback" in text
    assert reported == [error]


def test_an_uncaught_exception_in_a_worker_thread_is_logged_and_reported(tmp_path: Path) -> None:
    reported: list[BaseException] = []
    path = logs.setup_logging(tmp_path, on_error=reported.append)
    assert path is not None

    def fails() -> None:
        raise OSError("disc desconnectat")

    worker = threading.Thread(target=fails, name="exportacio")
    worker.start()
    worker.join()
    flush()
    text = path.read_text(encoding="utf-8")
    assert "exportacio" in text and "disc desconnectat" in text
    assert len(reported) == 1 and isinstance(reported[0], OSError)
