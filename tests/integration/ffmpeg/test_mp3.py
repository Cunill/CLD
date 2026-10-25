"""C04: convert_to_mp3 with the real FFmpeg (libmp3lame, 48 kHz stereo, ID3 tags, cancel, atomic write)."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from passimaker import ffmpeg
from passimaker.common import CancelToken
from passimaker.ffmpeg._process import os_path
from tests.fixtures.generate import find_ffmpeg
from tests.integration.ffmpeg.conftest import read_pcm

TAGS = ffmpeg.Mp3Tags(
    title="Cançó d'estiu — l'àvia ☀️🎶",
    artist="Grup de l'Escola Pérez & Ñoño 🎸",
    comment="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
)


def _ffprobe(path: Path) -> dict[str, Any]:
    args = [str(ffmpeg.locate().ffprobe), "-v", "error", "-print_format", "json"]
    args += ["-show_format", "-show_streams", "file:" + os_path(path)]
    out = subprocess.run(args, check=True, capture_output=True).stdout
    return json.loads(out.decode("utf-8"))


def _tags(info: dict[str, Any]) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (info["format"].get("tags") or {}).items()}


def _leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


@pytest.fixture(scope="module")
def long_song(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Five minutes of tone in FLAC (small file, a few seconds of MP3 encoding)."""
    path = tmp_path_factory.mktemp("llarga") / "cançó llarga.flac"
    cmd = [find_ffmpeg(), "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi"]
    cmd += ["-i", "sine=frequency=440:sample_rate=48000:duration=300", "-ac", "2", "-c:a", "flac", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.mark.parametrize("name", ["tone_440.wav", "tone_660.m4a", "tone_880.mp3", "tone_440.ogg"])
def test_converts_to_48k_stereo_cbr_with_same_duration(
    fixture_files: dict[str, Path], tmp_path: Path, name: str
) -> None:
    source = fixture_files[name]
    dest = tmp_path / "sortida.mp3"
    ffmpeg.convert_to_mp3(source, dest, 192, ffmpeg.Mp3Tags())
    info = ffmpeg.probe(dest)
    assert abs(info.duration_s - ffmpeg.probe(source).duration_s) <= 0.050
    assert info.sample_rate == 48000
    assert info.channels == 2
    assert not info.has_video
    (stream,) = _ffprobe(dest)["streams"]
    assert stream["codec_name"] == "mp3"
    assert int(stream["bit_rate"]) == 192000
    assert _leftovers(tmp_path) == ["sortida.mp3"]


@pytest.mark.parametrize("kbps", [128, 320])
def test_bitrate_is_constant_and_as_requested(
    fixture_files: dict[str, Path], tmp_path: Path, kbps: int
) -> None:
    dest = tmp_path / "sortida.mp3"
    ffmpeg.convert_to_mp3(fixture_files["tone_440.wav"], dest, kbps, ffmpeg.Mp3Tags())
    (stream,) = _ffprobe(dest)["streams"]
    assert int(stream["bit_rate"]) == kbps * 1000
    # Constant bitrate: the size follows the duration (8 s), plus headers and padding.
    expected = kbps * 1000 / 8 * 8.0
    assert expected * 0.98 <= dest.stat().st_size <= expected * 1.05


def test_mono_and_44k_become_48k_stereo(mono_wav: Path, wav_44k: Path, tmp_path: Path) -> None:
    for source in (mono_wav, wav_44k):
        dest = tmp_path / f"{source.stem}.mp3"
        ffmpeg.convert_to_mp3(source, dest, 192, ffmpeg.Mp3Tags())
        info = ffmpeg.probe(dest)
        assert (info.sample_rate, info.channels) == (48000, 2)
        assert abs(info.duration_s - ffmpeg.probe(source).duration_s) <= 0.050


def test_mono_keeps_its_level_on_both_sides(mono_wav: Path, tmp_path: Path) -> None:
    dest = tmp_path / "mono.mp3"
    ffmpeg.convert_to_mp3(mono_wav, dest, 192, ffmpeg.Mp3Tags())
    original = read_pcm(ffmpeg.decode_audio(mono_wav, tmp_path / "a.f32").path)
    converted = read_pcm(ffmpeg.decode_audio(dest, tmp_path / "b.f32").path)
    np.testing.assert_allclose(converted[:, 0], converted[:, 1], atol=1e-6)
    rms = float(np.sqrt(np.mean(converted[:, 0] ** 2)))
    assert rms == pytest.approx(float(np.sqrt(np.mean(original[:, 0] ** 2))), rel=0.05)


def test_tags_with_accents_and_emojis_are_readable_and_there_is_no_cover(
    fixture_files: dict[str, Path], photo_jpg: Path, tmp_path: Path
) -> None:
    # A source with its own tags and a cover: only the requested tags reach the MP3, without the picture.
    source = tmp_path / "amb portada.mp3"
    cmd = [find_ffmpeg(), "-nostdin", "-loglevel", "error", "-y", "-i", str(fixture_files["tone_660.wav"])]
    cmd += ["-i", str(photo_jpg), "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-c:v", "copy"]
    cmd += ["-disposition:v", "attached_pic", "-metadata", "album=Àlbum original", str(source)]
    subprocess.run(cmd, check=True, capture_output=True)
    dest = tmp_path / "amb etiquetes.mp3"
    ffmpeg.convert_to_mp3(source, dest, 192, TAGS)
    info = _ffprobe(dest)
    assert [s["codec_type"] for s in info["streams"]] == ["audio"]
    tags = _tags(info)
    assert tags["title"] == TAGS.title
    assert tags["artist"] == TAGS.artist
    assert tags["comment"] == TAGS.comment
    assert "album" not in tags


def test_empty_tags_are_not_written(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    dest = tmp_path / "sense títol.mp3"
    ffmpeg.convert_to_mp3(fixture_files["tone_440.wav"], dest, 192, ffmpeg.Mp3Tags(title="Només el títol"))
    tags = _tags(_ffprobe(dest))
    assert tags["title"] == "Només el títol"
    assert "artist" not in tags and "comment" not in tags


def test_paths_with_accents_emojis_and_dashes(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    folder = tmp_path / "Música d'en Pérez 🎵" / "àèéíòóú ïü ç ñ €"
    folder.mkdir(parents=True)
    source = folder / "-Cançó original, 1 🎧.m4a"
    source.write_bytes(fixture_files["tone_660.m4a"].read_bytes())
    dest = folder / "-Cançó convertida, 1 🎶.mp3"
    ffmpeg.convert_to_mp3(source, dest, 192, TAGS)
    assert abs(ffmpeg.probe(dest).duration_s - 6.0) <= 0.050
    assert _tags(_ffprobe(dest))["title"] == TAGS.title
    assert _leftovers(folder) == sorted([source.name, dest.name])


def test_progress_never_goes_back_and_ends_at_total(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []
    dest = tmp_path / "progrés.mp3"
    ffmpeg.convert_to_mp3(
        fixture_files["tone_880.wav"], dest, 192, ffmpeg.Mp3Tags(), progress=lambda d, t: calls.append((d, t))
    )
    assert calls
    totals = {t for _, t in calls}
    assert totals == {10_000}  # milliseconds of the 10 s tone
    done = [d for d, _ in calls]
    assert done == sorted(done)
    assert all(0 <= d <= 10_000 for d in done)
    assert calls[-1] == (10_000, 10_000)


def test_existing_destination_is_replaced_only_at_the_end(
    fixture_files: dict[str, Path], tmp_path: Path
) -> None:
    dest = tmp_path / "ja existeix.mp3"
    dest.write_bytes(b"old")
    seen: list[bytes] = []
    ffmpeg.convert_to_mp3(
        fixture_files["tone_440.wav"],
        dest,
        192,
        ffmpeg.Mp3Tags(),
        progress=lambda d, t: seen.append(dest.read_bytes()),
    )
    assert seen[:-1] and all(content == b"old" for content in seen[:-1])
    assert abs(ffmpeg.probe(dest).duration_s - 8.0) <= 0.050
    assert _leftovers(tmp_path) == ["ja existeix.mp3"]


def test_file_without_audio(photo_jpg: Path, tmp_path: Path) -> None:
    dest = tmp_path / "res.mp3"
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.convert_to_mp3(photo_jpg, dest, 192, TAGS)
    assert caught.value.message_key == ffmpeg.ERROR_NO_AUDIO
    assert _leftovers(tmp_path) == []


def test_missing_and_unreadable_sources(tmp_path: Path) -> None:
    dest = tmp_path / "res.mp3"
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.convert_to_mp3(tmp_path / "no hi és.wav", dest, 192, TAGS)
    assert caught.value.message_key == ffmpeg.ERROR_FILE_NOT_FOUND
    broken = tmp_path / "trencat.m4a"
    broken.write_bytes(b"no som pas audio" * 100)
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.convert_to_mp3(broken, dest, 192, TAGS)
    assert caught.value.message_key == ffmpeg.ERROR_UNREADABLE
    assert _leftovers(tmp_path) == ["trencat.m4a"]


def test_missing_destination_folder_is_a_write_error(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    dest = tmp_path / "no existeix" / "sortida.mp3"
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.convert_to_mp3(fixture_files["tone_440.wav"], dest, 192, TAGS)
    assert caught.value.message_key == ffmpeg.ERROR_WRITE
    assert _leftovers(tmp_path) == []


def test_already_cancelled_does_nothing(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    cancel = CancelToken()
    cancel.cancel()
    ffmpeg.convert_to_mp3(fixture_files["tone_440.wav"], tmp_path / "res.mp3", 192, TAGS, cancel=cancel)
    assert _leftovers(tmp_path) == []


def test_cancel_halfway_stops_quickly_and_leaves_no_files(long_song: Path, tmp_path: Path) -> None:
    dest = tmp_path / "a mitges.mp3"
    dest.write_bytes(b"old")
    cancel = CancelToken()
    cancelled_at: list[float] = []

    def on_progress(done: int, total: int) -> None:
        if not cancelled_at and done >= 1000:
            cancelled_at.append(time.monotonic())
            cancel.cancel()

    ffmpeg.convert_to_mp3(long_song, dest, 192, TAGS, progress=on_progress, cancel=cancel)
    assert cancelled_at, "la conversió ha d'haver començat"
    assert time.monotonic() - cancelled_at[0] < 2.0
    assert _leftovers(tmp_path) == ["a mitges.mp3"]
    assert dest.read_bytes() == b"old"


def test_cancel_from_another_thread(long_song: Path, tmp_path: Path) -> None:
    dest = tmp_path / "des d'un altre fil.mp3"
    cancel = CancelToken()
    timer = threading.Timer(0.5, cancel.cancel)
    timer.start()
    begin = time.monotonic()
    ffmpeg.convert_to_mp3(long_song, dest, 192, TAGS, cancel=cancel)
    timer.join()
    assert cancel.cancelled
    assert time.monotonic() - begin < 2.5
    assert _leftovers(tmp_path) == []


@pytest.mark.lent
def test_long_song_converts_completely(long_song: Path, tmp_path: Path) -> None:
    dest = tmp_path / "llarga.mp3"
    ffmpeg.convert_to_mp3(long_song, dest, 192, TAGS, cancel=CancelToken())
    assert abs(ffmpeg.probe(dest).duration_s - 300.0) <= 0.050
