"""Running ffmpeg/ffprobe: no shell, no console window, Unicode and long paths, stderr always drained.

This is the only place in PassiMaker that starts processes (architecture rule 7).
"""

from __future__ import annotations

import collections
import contextlib
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from passimaker.ffmpeg.types import (
    ERROR_DISK_FULL,
    ERROR_FILE_NOT_FOUND,
    ERROR_NOT_FOUND,
    ERROR_TIMEOUT,
    ERROR_WRITE,
    FfmpegError,
)

CREATE_NO_WINDOW = 0x08000000
"""Windows process creation flag: console programs start without opening a console window."""

STDERR_TAIL_BYTES = 64 * 1024
"""How much of ffmpeg's error output is kept for error messages (the rest is read and discarded)."""

DETAIL_CHARS = 1500
"""Characters of ffmpeg's error output copied into FfmpegError.detail."""

_WINDOWS_MAX_PATH = 240
"""Below MAX_PATH (260) with margin: from this length on, Windows needs the extended-length prefix."""

_DISK_FULL_MARKERS = ("No space left on device", "There is not enough space on the disk")
_WRITE_MARKERS = ("Permission denied", "No such file or directory", "Read-only file system")


def creation_flags(platform: str = sys.platform) -> int:
    """No console window on Windows (0 elsewhere, where the option does not exist)."""
    return CREATE_NO_WINDOW if platform == "win32" else 0


def os_path(path: Path, platform: str = sys.platform) -> str:
    """Path for Python's own file operations; long Windows paths get the extended-length prefix."""
    text = str(path.absolute())
    if platform != "win32" or len(text) < _WINDOWS_MAX_PATH or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def media_url(path: Path) -> str:
    """Path argument for ffmpeg: absolute and with the file: protocol, so that names containing ':'
    or starting with '-' are never read as options or protocols. FFmpeg itself handles long paths
    on Windows (it adds the extended-length prefix)."""
    return "file:" + str(path.absolute())


def require_file(path: Path) -> None:
    if not Path(os_path(path)).is_file():
        raise FfmpegError(ERROR_FILE_NOT_FOUND, str(path))


def remove_file(path: Path, timeout_s: float = 1.5) -> None:
    """Deletes path if it is a regular file (never a folder or a device such as /dev/null).

    On Windows a process that has just been killed may hold the file for a moment: retry.
    """
    target = Path(os_path(path))
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if target.is_file():
                target.unlink()
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def classify(stderr: str, default_key: str, *, writing: bool = False) -> str:
    """Message key for an ffmpeg failure, from its error output."""
    if any(marker in stderr for marker in _DISK_FULL_MARKERS):
        return ERROR_DISK_FULL
    if writing and any(marker in stderr for marker in _WRITE_MARKERS):
        return ERROR_WRITE
    return default_key


def error_detail(stderr: str) -> str:
    text = stderr.strip()
    return text[-DETAIL_CHARS:]


@dataclass(frozen=True, slots=True)
class RunResult:
    returncode: int
    stdout: bytes
    stderr: str


def _start(args: Sequence[str], stdin: int | None, stdout: int | None) -> subprocess.Popen[bytes]:
    try:
        return subprocess.Popen(
            list(args),
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            creationflags=creation_flags(),
        )
    except FileNotFoundError as error:
        raise FfmpegError(ERROR_NOT_FOUND, args[0]) from error


def run(args: Sequence[str], timeout_s: float) -> RunResult:
    """Runs to completion, reading stdout and stderr at the same time (no pipe can fill up)."""
    process = _start(args, subprocess.DEVNULL, subprocess.PIPE)
    try:
        out, err = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise FfmpegError(ERROR_TIMEOUT, f"{Path(args[0]).name}: {timeout_s:.0f} s") from error
    return RunResult(process.returncode, out, err.decode("utf-8", errors="replace"))


class _StderrDrain(threading.Thread):
    """Reads a process's stderr until it closes, keeping only the last STDERR_TAIL_BYTES."""

    def __init__(self, stream: IO[bytes]) -> None:
        super().__init__(name="ffmpeg-stderr", daemon=True)
        self._stream = stream
        self._chunks: collections.deque[bytes] = collections.deque()
        self._size = 0
        self._lock = threading.Lock()

    def run(self) -> None:
        read = getattr(self._stream, "read1", self._stream.read)
        try:
            while chunk := read(65536):
                with self._lock:
                    self._chunks.append(chunk)
                    self._size += len(chunk)
                    while self._size - len(self._chunks[0]) >= STDERR_TAIL_BYTES:
                        self._size -= len(self._chunks.popleft())
        except (OSError, ValueError):
            pass  # The pipe was closed under us (abort).

    def text(self) -> str:
        with self._lock:
            data = b"".join(self._chunks)
        return data[-STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")


class StreamingProcess:
    """A running ffmpeg with an optional stdin and/or stdout pipe and a drained stderr."""

    def __init__(self, args: Sequence[str], *, stdin: bool, stdout: bool) -> None:
        self.args = list(args)
        self.process = _start(
            args,
            subprocess.PIPE if stdin else subprocess.DEVNULL,
            subprocess.PIPE if stdout else subprocess.DEVNULL,
        )
        assert self.process.stderr is not None
        self._drain = _StderrDrain(self.process.stderr)
        self._drain.start()

    @property
    def stdin(self) -> IO[bytes]:
        assert self.process.stdin is not None
        return self.process.stdin

    @property
    def stdout(self) -> IO[bytes]:
        assert self.process.stdout is not None
        return self.process.stdout

    def wait(self, timeout_s: float | None = None) -> int:
        """Waits for the process to end and for stderr to be fully read; returns the exit code."""
        if self.process.stdin is not None and not self.process.stdin.closed:
            # If ffmpeg already exited, closing fails: the exit code tells what happened.
            with contextlib.suppress(OSError):
                self.process.stdin.close()
        try:
            code = self.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired as error:
            self.kill()
            raise FfmpegError(ERROR_TIMEOUT, f"{Path(self.args[0]).name}: {timeout_s:.0f} s") from error
        self._drain.join(timeout=5)
        self._close_pipes()
        return code

    def kill(self) -> None:
        """Stops the process at once (no-op if it already ended) and releases the pipes."""
        if self.process.poll() is None:
            self.process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):  # the OS did not kill it (never seen)
            self.process.wait(timeout=5)
        self._close_pipes()
        self._drain.join(timeout=1)

    def stderr_text(self) -> str:
        return self._drain.text()

    def _close_pipes(self) -> None:
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()
