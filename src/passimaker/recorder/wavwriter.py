"""The temporary WAV, written while recording and deleted on any interruption (block C09).

32-bit float, little-endian, with a fixed 58-byte header (RIFF, fmt with cbSize, fact, data) that
close() rewrites with the final sizes; read_frames() reads only the WAVs written here.
"""

from __future__ import annotations

import contextlib
import logging
import os
import struct
import tempfile
from pathlib import Path
from typing import BinaryIO

import numpy as np

from passimaker.recorder.types import AudioFrames

TEMP_PREFIX = "passimaker_gravacio_"
"""Temporary WAVs are `<temp_dir>/passimaker_gravacio_*.wav` (32-bit float)."""
TEMP_SUFFIX = ".wav"
_FMT = struct.Struct("<HHIIHHH")
HEADER_BYTES = 12 + 8 + _FMT.size + 8 + 4 + 8
"""RIFF/WAVE + fmt chunk + fact chunk + data chunk header: the samples start here."""
_SAMPLE_BYTES = 4
_FORMAT_FLOAT = 3

_log = logging.getLogger(__name__)


class TempWav:
    """A new temporary WAV in `temp_dir`; write() blocks, then close() (keep) or delete()."""

    def __init__(self, temp_dir: Path, sample_rate: int, channels: int) -> None:
        handle, name = tempfile.mkstemp(prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX, dir=temp_dir)
        self.path = Path(name)
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames = 0
        self._file: BinaryIO | None = os.fdopen(handle, "wb")
        try:
            self._file.write(self._header())
        except BaseException:
            self.delete()
            raise

    def write(self, block: AudioFrames) -> None:
        """Appends `block` (frames, channels); OSError (e.g. disk full) is the caller's to handle."""
        if self._file is None:
            raise ValueError("the WAV is closed")
        self._file.write(np.ascontiguousarray(block, dtype="<f4").tobytes())
        self.frames += block.shape[0]

    def close(self) -> None:
        """Finish the header and close the file, which stays on disk. Does nothing if already closed."""
        if self._file is None:
            return
        file, self._file = self._file, None
        try:
            file.seek(0)
            file.write(self._header())
        finally:
            file.close()

    def delete(self) -> None:
        """Close and delete the file, whatever happened before (never raises)."""
        if self._file is not None:
            file, self._file = self._file, None
            with contextlib.suppress(OSError):
                file.close()
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:  # e.g. still open by another program: remove_leftovers() at the next start
            _log.warning("Could not delete the temporary WAV %s: %s", self.path, error)

    def _header(self) -> bytes:
        data_bytes = self.frames * self.channels * _SAMPLE_BYTES
        block_align = self.channels * _SAMPLE_BYTES
        fmt = _FMT.pack(
            _FORMAT_FLOAT, self.channels, self.sample_rate, self.sample_rate * block_align, block_align, 32, 0
        )
        return (
            b"RIFF"
            + struct.pack("<I", HEADER_BYTES - 8 + data_bytes)
            + b"WAVE"
            + b"fmt "
            + struct.pack("<I", len(fmt))
            + fmt
            + b"fact"
            + struct.pack("<II", 4, self.frames)
            + b"data"
            + struct.pack("<I", data_bytes)
        )


def read_info(path: Path) -> tuple[int, int, int]:
    """`(sample_rate, channels, frames)` of a WAV written by TempWav."""
    with path.open("rb") as file:
        header = file.read(HEADER_BYTES)
    if len(header) < HEADER_BYTES or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise ValueError(f"not a WAV written by the recorder: {path}")
    tag, channels, rate, _, _, bits, _ = _FMT.unpack_from(header, 20)
    if tag != _FORMAT_FLOAT or bits != 32:
        raise ValueError(f"not a 32-bit float WAV: {path}")
    (data_bytes,) = struct.unpack_from("<I", header, HEADER_BYTES - 4)
    return rate, channels, data_bytes // (channels * _SAMPLE_BYTES)


def read_frames(path: Path, start: int = 0, count: int | None = None) -> AudioFrames:
    """Frames `start`…`start + count` (to the end if None) of a WAV written by TempWav."""
    _, channels, frames = read_info(path)
    start = min(max(0, start), frames)
    count = frames - start if count is None else max(0, min(count, frames - start))
    with path.open("rb") as file:
        file.seek(HEADER_BYTES + start * channels * _SAMPLE_BYTES)
        data = file.read(count * channels * _SAMPLE_BYTES)
    return np.frombuffer(data, dtype="<f4").astype(np.float32).reshape(-1, channels)


def remove_leftovers(temp_dir: Path) -> int:
    """Delete the temporary WAVs left by an unexpected close; the number deleted.

    Called when the program opens (G1: an interrupted recording is never recovered). A WAV that
    cannot be deleted (on Windows, one another PassiMaker is still recording) is left alone.
    """
    removed = 0
    try:
        candidates = sorted(temp_dir.glob(f"{TEMP_PREFIX}*{TEMP_SUFFIX}"))
    except OSError:
        return 0
    for path in candidates:
        try:
            if path.is_file() and not path.is_symlink():
                path.unlink()
                removed += 1
        except OSError as error:
            _log.info("Temporary WAV %s left in place: %s", path, error)
    if removed:
        _log.info("Deleted %d temporary WAV(s) of interrupted recordings", removed)
    return removed
