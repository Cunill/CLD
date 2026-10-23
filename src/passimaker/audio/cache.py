"""Decoded songs and their loudness, kept in a cache folder so each song is decoded only once.

Each song is decoded whole (not trimmed): changing the trim, the fades or the volume does not
decode it again. The key is the absolute path, the size and the modification time of the file;
if the file changes, it gets a new key. Files are written under a temporary name and renamed,
so another thread or process never reads a half-written file.

The folder stays under ``CACHE_LIMIT_BYTES``: after a song is decoded, the songs used least
recently (modification time, refreshed on every use) are deleted, except the ones this process
has in use.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from passimaker.audio.params import CACHE_LIMIT_BYTES, CACHE_VERSION, CHANNELS
from passimaker.common import AudioBlock
from passimaker.ffmpeg import (
    ERROR_FILE_NOT_FOUND,
    FfmpegError,
    Loudness,
    decode_audio,
    measure_loudness,
)

PCM_SUFFIX = ".f32"
LOUDNESS_SUFFIX = ".lufs.json"
FRAME_BYTES = CHANNELS * 4

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_in_use: set[Path] = set()
"""Decoded songs this process has handed out: never deleted to make room (a preview may be reading them)."""
_log = logging.getLogger(__name__)


def _lock(key: str) -> threading.Lock:
    """One lock per cache entry: two threads preparing the same song decode it only once."""
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


@dataclass(frozen=True, slots=True)
class DecodedSong:
    """A whole song as raw little-endian float32 stereo at 48 kHz (see passimaker.ffmpeg.PcmFile)."""

    path: Path
    frames: int

    def read(self, first: int, count: int) -> AudioBlock:
        """Frames [first, first + count) of the song; zeros outside the file. Thread-safe."""
        block = np.zeros((count, CHANNELS), dtype=np.float32)
        lo, hi = max(0, first), min(self.frames, first + count)
        if hi > lo:
            data = np.fromfile(self.path, dtype="<f4", count=(hi - lo) * CHANNELS, offset=lo * FRAME_BYTES)
            got = len(data) // CHANNELS
            block[lo - first : lo - first + got] = data[: got * CHANNELS].reshape(got, CHANNELS)
        return block


def song_key(path: Path) -> str:
    """Cache key of a song file; FfmpegError(file_not_found) if it cannot be read."""
    try:
        absolute = path.resolve()
        stat = absolute.stat()
    except OSError as error:
        raise FfmpegError(ERROR_FILE_NOT_FOUND, str(path)) from error
    text = f"{CACHE_VERSION}|{absolute}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()[:32]


def _temporary(final: Path) -> Path:
    return final.with_name(f"{final.name}.{os.getpid()}-{threading.get_ident()}.tmp")


def _publish(temporary: Path, final: Path) -> None:
    """Renames temporary to final; if another process got there first, keeps its file."""
    try:
        temporary.replace(final)
    except OSError:
        if not final.is_file():
            raise
        with contextlib.suppress(OSError):
            temporary.unlink()


def decoded_song(path: Path, cache_dir: Path) -> DecodedSong:
    """Decodes the song into cache_dir the first time; afterwards only checks the file."""
    key = song_key(path)
    final = cache_dir / f"{key}{PCM_SUFFIX}"
    with _lock(key):
        decoded = not final.is_file()
        if decoded:
            temporary = _temporary(final)
            decode_audio(path, temporary)
            _publish(temporary, final)
        else:
            with contextlib.suppress(OSError):
                os.utime(final)  # recently used: the last to go
        with _locks_guard:
            _in_use.add(final)
        song = DecodedSong(final, final.stat().st_size // FRAME_BYTES)
    if decoded:
        prune(cache_dir, CACHE_LIMIT_BYTES)
    return song


def prune(cache_dir: Path, limit_bytes: int) -> None:
    """Deletes the least recently used decoded songs (and their loudness) until the folder is
    under limit_bytes. Never raises: a file another process holds open is left for later."""
    entries: list[tuple[float, int, Path]] = []
    try:
        for path in cache_dir.glob(f"*{PCM_SUFFIX}"):
            with contextlib.suppress(OSError):
                stat = path.stat()
                entries.append((stat.st_mtime, stat.st_size, path))
    except OSError:
        return
    total = sum(size for _, size, _ in entries)
    with _locks_guard:
        in_use = set(_in_use)
    for _, size, path in sorted(entries, key=lambda entry: entry[0]):
        if total <= limit_bytes:
            break
        if path in in_use:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        with contextlib.suppress(OSError):
            path.with_name(path.name.removesuffix(PCM_SUFFIX) + LOUDNESS_SUFFIX).unlink()
        total -= size
        _log.info("Audio cache over its limit, deleted %s (%d MB)", path.name, size // 2**20)


def song_loudness(path: Path, cache_dir: Path) -> Loudness:
    """EBU R128 loudness of the whole song, measured once and kept in cache_dir."""
    key = song_key(path)
    final = cache_dir / f"{key}{LOUDNESS_SUFFIX}"
    with _lock(key + LOUDNESS_SUFFIX):
        cached = _read_loudness(final)
        if cached is not None:
            return cached
        loudness = measure_loudness(path)
        temporary = _temporary(final)
        data = {"integrated_lufs": loudness.integrated_lufs, "true_peak_dbfs": loudness.true_peak_dbfs}
        temporary.write_text(json.dumps(data), encoding="utf-8")
        _publish(temporary, final)
        return loudness


def _read_loudness(path: Path) -> Loudness | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Loudness(float(data["integrated_lufs"]), float(data["true_peak_dbfs"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
