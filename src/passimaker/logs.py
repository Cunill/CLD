"""The error log (block B15): a file that renews itself, and nothing that ends without a trace.

``setup_logging`` sends the warnings and errors of every module to
``%LOCALAPPDATA%\\PassiMaker\\logs\\passimaker.log`` (5 files of 5 MB at most: the oldest is
dropped) and installs hooks so that an exception nobody caught, in any thread, is written there
before anything else happens. The interface adds its own hook on top to tell the user (rule 1:
no Qt here).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

LOG_ENV_VAR = "PASSIMAKER_LOGS"
"""Folder for the log; takes precedence over the default (tests point it to a temporary folder)."""
LOG_FILE_NAME = "passimaker.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_COUNT = 5
"""The current file and four old ones (PLA, B15: 5 files of 5 MB)."""
LOG_FORMAT = "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"

_log = logging.getLogger("passimaker")

type ErrorHook = Callable[[BaseException], None]
"""Called after an uncaught exception has been logged (the interface shows a message)."""


def log_dir() -> Path:
    """%LOCALAPPDATA%\\PassiMaker\\logs on Windows; ~/.local/state/passimaker/logs elsewhere."""
    override = os.environ.get(LOG_ENV_VAR)
    if override:
        return Path(override)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "PassiMaker" / "logs"
    xdg = os.environ.get("XDG_STATE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "state") / "passimaker" / "logs"


def setup_logging(folder: Path | None = None, *, on_error: ErrorHook | None = None) -> Path | None:
    """Writes the log to ``folder`` (default ``log_dir()``) and logs every uncaught exception.

    Returns the log file, or None if the folder cannot be written: the program then goes on
    without a log rather than not starting. Calling it again replaces the previous file handler.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in [h for h in root.handlers if isinstance(h, RotatingFileHandler)]:
        root.removeHandler(handler)
        handler.close()
    path: Path | None = (folder if folder is not None else log_dir()) / LOG_FILE_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_FILE_COUNT - 1, encoding="utf-8", delay=True
        )
    except OSError:
        path = None
    else:
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    install_exception_hooks(on_error)
    from passimaker import __version__

    _log.info("PassiMaker %s, Python %s, %s", __version__, sys.version.split()[0], sys.platform)
    return path


def install_exception_hooks(on_error: ErrorHook | None = None) -> None:
    """An exception nobody caught, in the main thread or in any other, goes to the log first."""

    def main_hook(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, error, trace)
            return
        _log.critical("Uncaught exception", exc_info=(kind, error, trace))
        if on_error is not None:
            on_error(error)

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is None or issubclass(args.exc_type, SystemExit):
            return
        name = args.thread.name if args.thread is not None else "?"
        _log.critical(
            "Uncaught exception in thread %s",
            name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        if on_error is not None:
            on_error(args.exc_value)

    sys.excepthook = main_hook
    threading.excepthook = thread_hook
