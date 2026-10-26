"""C09: the temporary WAV (32-bit float, written as it records) and remove_leftovers (G1)."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from passimaker.recorder import TEMP_PREFIX, remove_leftovers
from passimaker.recorder.wavwriter import HEADER_BYTES, TempWav, read_frames, read_info


def test_writes_a_float_wav_as_it_records(tmp_path: Path) -> None:
    wav = TempWav(tmp_path, 44100, 2)
    assert wav.path.parent == tmp_path and wav.path.name.startswith(TEMP_PREFIX) and wav.path.suffix == ".wav"
    blocks = [np.full((n, 2), n / 1000, dtype=np.float32) for n in (100, 1, 333)]
    for block in blocks:
        wav.write(block)
    wav.close()
    wav.close()
    assert read_info(wav.path) == (44100, 2, 434)
    np.testing.assert_array_equal(read_frames(wav.path), np.concatenate(blocks))
    np.testing.assert_array_equal(read_frames(wav.path, 100, 2), np.concatenate(blocks)[100:102])
    header = wav.path.read_bytes()[:HEADER_BYTES]
    assert header[:4] == b"RIFF" and header[8:16] == b"WAVEfmt "
    assert wav.path.stat().st_size == HEADER_BYTES + 434 * 2 * 4
    assert struct.unpack_from("<I", header, 4)[0] == wav.path.stat().st_size - 8
    with pytest.raises(ValueError):
        wav.write(blocks[0])


def test_delete_removes_it_whatever_happened(tmp_path: Path) -> None:
    wav = TempWav(tmp_path, 48000, 1)
    wav.write(np.zeros((10, 1), dtype=np.float32))
    wav.delete()
    wav.delete()
    assert list(tmp_path.iterdir()) == []
    closed = TempWav(tmp_path, 48000, 1)
    closed.close()
    closed.delete()
    assert list(tmp_path.iterdir()) == []


def test_reads_only_its_own_wavs(tmp_path: Path) -> None:
    other = tmp_path / "other.wav"
    other.write_bytes(b"RIFF" + bytes(60))
    with pytest.raises(ValueError):
        read_info(other)


def test_remove_leftovers_deletes_only_the_temporary_wavs(tmp_path: Path) -> None:
    for name in (f"{TEMP_PREFIX}abc.wav", f"{TEMP_PREFIX}def.wav"):
        (tmp_path / name).write_bytes(b"x")
    keep = [tmp_path / "song.wav", tmp_path / f"{TEMP_PREFIX}notes.txt", tmp_path / "passimaker_other.wav"]
    for path in keep:
        path.write_bytes(b"x")
    (tmp_path / f"{TEMP_PREFIX}folder.wav").mkdir()
    assert remove_leftovers(tmp_path) == 2
    assert sorted(tmp_path.iterdir()) == sorted([*keep, tmp_path / f"{TEMP_PREFIX}folder.wav"])
    assert remove_leftovers(tmp_path) == 0
    assert remove_leftovers(tmp_path / "missing") == 0
