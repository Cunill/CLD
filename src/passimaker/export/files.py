"""File operations of the export that must work with long Windows paths and files still held."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_WINDOWS_MAX_PATH = 248
"""Below this length every Windows API accepts the path as it is (MAX_PATH minus a file name)."""

REMOVE_RETRY_S = 1.5
"""A process that has just been stopped may hold its output for a moment on Windows."""


def long_path(path: Path, platform: str = sys.platform) -> Path:
    """The path for Python's own file operations: long Windows paths get the extended-length prefix
    (same rule as passimaker.ffmpeg, which does it for its own files)."""
    text = str(path.absolute())
    if platform != "win32" or len(text) < _WINDOWS_MAX_PATH or text.startswith("\\\\?\\"):
        return Path(text)
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def is_file(path: Path) -> bool:
    return long_path(path).is_file()


def remove_quietly(path: Path) -> None:
    """Deletes a leftover file, retrying for a moment if it is still in use; never raises."""
    target = long_path(path)
    deadline = time.monotonic() + REMOVE_RETRY_S
    while True:
        try:
            target.unlink(missing_ok=True)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                return
            time.sleep(0.02)
        except OSError:
            return


def replace(source: Path, dest: Path) -> None:
    long_path(source).replace(long_path(dest))
