"""B7: accents, spaces and long paths; no console window; every failure has a message key."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from passimaker import ffmpeg
from passimaker.ffmpeg import _process
from passimaker.ffmpeg._process import os_path

KNOWN_KEYS = {
    ffmpeg.ERROR_NOT_FOUND,
    ffmpeg.ERROR_FILE_NOT_FOUND,
    ffmpeg.ERROR_UNREADABLE,
    ffmpeg.ERROR_NO_AUDIO,
    ffmpeg.ERROR_DISK_FULL,
    ffmpeg.ERROR_WRITE,
    ffmpeg.ERROR_ENCODE,
    ffmpeg.ERROR_ABORTED,
    ffmpeg.ERROR_TIMEOUT,
    ffmpeg.ERROR_FAILED,
}


def _long_folder(base: Path) -> Path:
    """A folder with accents, spaces and an apostrophe, more than 260 characters long."""
    folder = base / "Música i fotos d'en Pérez" / "àèéíòóú ïü ç ñ €"
    while len(str(folder.absolute())) <= 280:
        folder = folder / "carpeta amb un nom força llarg"
    Path(os_path(folder)).mkdir(parents=True)
    return folder


def _copy(src: Path, dest: Path) -> Path:
    shutil.copyfile(src, os_path(dest))
    return dest


@pytest.fixture
def long_folder(tmp_path: Path) -> Path:
    return _long_folder(tmp_path)


def test_everything_works_with_accents_spaces_and_long_paths(
    fixture_files: dict[str, Path], long_folder: Path
) -> None:
    song = _copy(fixture_files["tone_440.mp3"], long_folder / "-Cançó número 1 (versió llarga).mp3")
    wav = _copy(fixture_files["tone_660.wav"], long_folder / "Àudio del passi.wav")
    assert len(str(song.absolute())) > 260

    info = ffmpeg.probe(song)
    assert abs(info.duration_s - 8.0) <= 0.010
    pcm = ffmpeg.decode_audio(song, long_folder / "descodificació temporal.f32", 1.0, 2.0)
    assert pcm.frames == 48000
    assert Path(os_path(pcm.path)).stat().st_size == 48000 * 8
    assert ffmpeg.measure_loudness(song).integrated_lufs < -10
    assert ffmpeg.waveform(song, 50).shape == (50,)

    video = long_folder / "Vídeo del passi — estiu.mp4"
    writer = ffmpeg.open_encoder(video, 64, 48, wav, ffmpeg.EncoderSettings(preset="ultrafast"))
    for n in range(30):
        writer.write(np.full((48, 64, 3), 4 * n, dtype=np.uint8))
    writer.close()
    assert ffmpeg.probe(video).has_audio
    assert ffmpeg.extract_frames(video, [0.5])[0].shape == (48, 64, 3)

    aborted = long_folder / "Vídeo a mig fer.mp4"
    writer = ffmpeg.open_encoder(aborted, 64, 48, None)
    writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.abort()
    assert not Path(os_path(aborted)).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="':' no és vàlid en un nom de fitxer de Windows")
def test_names_that_look_like_protocols(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    song = _copy(fixture_files["tone_440.flac"], tmp_path / "concat:http:cançó.flac")
    assert ffmpeg.probe(song).has_audio


def test_processes_never_use_a_shell_or_open_a_console(
    fixture_files: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    real_popen = subprocess.Popen

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(_process.subprocess, "Popen", spy)
    song = fixture_files["tone_440.ogg"]
    ffmpeg.probe(song)
    ffmpeg.decode_audio(song, tmp_path / "a.f32", 0.0, 1.0)
    ffmpeg.measure_loudness(song)
    ffmpeg.waveform(song, 10)
    writer = ffmpeg.open_encoder(tmp_path / "v.mp4", 64, 48, None, ffmpeg.EncoderSettings(preset="ultrafast"))
    writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.close()
    ffmpeg.extract_frames(tmp_path / "v.mp4", [0.0])
    assert len(calls) >= 6
    for kwargs in calls:
        assert kwargs["shell"] is False
        assert kwargs["stdin"] is not None  # never inherits the console's input
        if sys.platform == "win32":
            assert kwargs["creationflags"] & _process.CREATE_NO_WINDOW


def _readers(path: Path, tmp_path: Path) -> list[Any]:
    return [
        lambda: ffmpeg.probe(path),
        lambda: ffmpeg.decode_audio(path, tmp_path / "x.f32"),
        lambda: ffmpeg.measure_loudness(path),
        lambda: ffmpeg.waveform(path, 10),
        lambda: ffmpeg.extract_frames(path, [0.0]),
    ]


def test_missing_files_have_their_own_key(tmp_path: Path) -> None:
    for read in _readers(tmp_path / "no existeix.mp3", tmp_path):
        with pytest.raises(ffmpeg.FfmpegError) as caught:
            read()
        assert caught.value.message_key == ffmpeg.ERROR_FILE_NOT_FOUND


@pytest.mark.parametrize("content", [b"", b"no soc una can\xc3\xa7o" * 100, bytes(range(256)) * 64])
def test_corrupt_files_are_unreadable(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "trencada.mp3"
    path.write_bytes(content)
    for read in _readers(path, tmp_path):
        with pytest.raises(ffmpeg.FfmpegError) as caught:
            read()
        assert caught.value.message_key == ffmpeg.ERROR_UNREADABLE
    assert not (tmp_path / "x.f32").exists()


def test_files_without_audio(photo_jpg: Path, tmp_path: Path) -> None:
    photo = photo_jpg
    for read in _readers(photo, tmp_path)[1:4]:
        with pytest.raises(ffmpeg.FfmpegError) as caught:
            read()
        assert caught.value.message_key == ffmpeg.ERROR_NO_AUDIO
    info = ffmpeg.probe(photo)
    assert not info.has_audio and info.sample_rate is None and info.channels is None


def test_audio_files_have_no_frames(fixture_files: dict[str, Path]) -> None:
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.extract_frames(fixture_files["tone_440.wav"], [0.0])
    assert caught.value.message_key == ffmpeg.ERROR_UNREADABLE


@pytest.mark.skipif(not Path("/dev/full").exists(), reason="cal /dev/full (Linux)")
def test_a_full_disk_has_its_own_key() -> None:
    # /dev/full accepts the file but fails every write with ENOSPC, as a full disk does.
    writer = ffmpeg.open_encoder(
        Path("/dev/full"), 320, 240, None, ffmpeg.EncoderSettings(preset="ultrafast")
    )
    rng = np.random.default_rng(1)
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        for _ in range(300):
            writer.write(rng.integers(0, 255, (240, 320, 3), dtype=np.uint8))
        writer.close()
    assert caught.value.message_key == ffmpeg.ERROR_DISK_FULL
    assert Path("/dev/full").exists()  # the partial-file cleanup never touches devices


def test_every_error_key_is_listed_and_namespaced() -> None:
    exported = {value for name, value in vars(ffmpeg).items() if name.startswith("ERROR_")}
    assert exported == KNOWN_KEYS
    assert all(key.startswith("ffmpeg.") for key in KNOWN_KEYS)
