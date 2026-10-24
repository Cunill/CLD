"""Decoding cache, unreadable songs, environment errors and the length of the mix."""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import numpy as np
import pytest

from passimaker import audio
from passimaker.audio import cache
from passimaker.ffmpeg import ERROR_DISK_FULL, ERROR_FILE_NOT_FOUND, ERROR_UNREADABLE, FfmpegError
from passimaker.timeline import compute_timeline
from tests.audio.conftest import SR, Mixer, level, project, read_wav, song


def forbid_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object, **__: object) -> None:
        raise AssertionError("no s'havia de cridar FFmpeg")

    monkeypatch.setattr(cache, "decode_audio", fail)
    monkeypatch.setattr(cache, "measure_loudness", fail)


def test_second_prepare_uses_the_cache(
    songs: dict[str, Path], mixer: Mixer, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = project(10.0, [song(songs, "440", trim=(1.0, 5.0)), song(songs, "660")])
    first = mixer(p).read(0.0, 10 * SR)
    forbid_ffmpeg(monkeypatch)
    # A different trim, fades and volume: still no decoding (the whole song is cached).
    q = project(10.0, [song(songs, "440", trim=(2.0, 4.0), fades=(1.0, 1.0), volume=0.7), song(songs, "660")])
    again = mixer(p)
    assert again.measured_gains_db.keys() == {"440", "660"}
    np.testing.assert_array_equal(again.read(0.0, 10 * SR), first)
    assert mixer(q).read(0.0, 10 * SR).any()


def test_a_changed_file_is_decoded_again(songs: dict[str, Path], mixer: Mixer, tmp_path: Path) -> None:
    path = tmp_path / "canviant.wav"
    shutil.copy(songs["440"], path)
    p = project(10.0, [song({"440": path}, "440")], normalize=False)
    assert level(mixer(p).read(0.0, 4 * SR), 440, SR, SR) > 0.2
    shutil.copy(songs["880"], path)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
    out = mixer(p).read(0.0, 4 * SR)
    assert level(out, 880, SR, SR) > 0.2 and level(out, 440, SR, SR) < 0.01


def test_concurrent_prepares_decode_once(
    songs: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    real = cache.decode_audio

    def counting(path: Path, dest: Path, *args: float) -> object:
        calls.append(path)
        return real(path, dest, *args)

    monkeypatch.setattr(cache, "decode_audio", counting)
    p = project(10.0, [song(songs, "660")])
    plan = compute_timeline(p).audio_plan
    results: list[np.ndarray] = []
    threads = [
        threading.Thread(target=lambda: results.append(audio.prepare(p, plan, tmp_path).read(0, SR)))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert len(results) == 4 and all(np.array_equal(r, results[0]) for r in results)
    assert not list(tmp_path.glob("*.tmp"))


def test_unreadable_songs_stay_silent_and_are_reported(songs: dict[str, Path], mixer: Mixer) -> None:
    missing = {"440": songs["440"].with_name("no existeix.mp3")}
    p = project(
        12.0,
        [
            song(songs, "corrupt", trim=(0.0, 3.0)),
            song(songs, "660", trim=(0.0, 3.0)),
            song(missing, "440", song_id="perduda", trim=(0.0, 3.0)),
        ],
    )
    mix = mixer(p)
    assert mix.failures.keys() == {"corrupt", "perduda"}
    assert mix.failures["corrupt"].message_key == ERROR_UNREADABLE
    assert mix.failures["perduda"].message_key == ERROR_FILE_NOT_FOUND
    out = mix.read(0.0, 9 * SR)
    assert not out[: 3 * SR].any()
    assert level(out, 660, 4 * SR, SR) > 0.05
    assert not out[6 * SR :].any()


def test_environment_errors_are_raised(
    songs: dict[str, Path], mixer: Mixer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_full(*_: object, **__: object) -> None:
        raise FfmpegError(ERROR_DISK_FULL, "")

    monkeypatch.setattr(cache, "decode_audio", disk_full)
    with pytest.raises(FfmpegError) as error:
        mixer(project(10.0, [song(songs, "880")]))
    assert error.value.message_key == ERROR_DISK_FULL


def test_the_mix_lasts_exactly_as_long_as_the_video(
    songs: dict[str, Path], mixer: Mixer, tmp_path: Path
) -> None:
    """Durations that are not whole frames (after fitting to the music): the WAV has total_frames × 1600."""
    p = project(10.0, [song(songs, "880")], photo_s=2.0123)
    timeline = compute_timeline(p)
    mix = mixer(p)
    assert mix.total_frames == timeline.total_frames * SR // timeline.fps
    mix.render_wav(tmp_path / "durada.wav")
    assert len(read_wav(tmp_path / "durada.wav")) == timeline.total_frames * 1600


def test_no_music_gives_silence(mixer: Mixer, tmp_path: Path) -> None:
    mix = mixer(project(6.0, []))
    assert mix.duration_s == 6.0 and not mix.read(1.0, SR).any()
    mix.render_wav(tmp_path / "silenci.wav")
    wav = read_wav(tmp_path / "silenci.wav")
    assert len(wav) == 6 * SR and not wav.any()


def test_songs_after_the_end_of_the_show_are_not_decoded(songs: dict[str, Path], mixer: Mixer) -> None:
    mix = mixer(project(4.0, [song(songs, "440"), song(songs, "corrupt")]))
    assert mix.failures == {}
    assert mix.measured_gains_db.keys() == {"440"}


# --- Size limit (B15) -----------------------------------------------------------------------------


def _stale_entry(folder: Path, name: str, size: int, age_s: float) -> Path:
    path = folder / f"{name}{cache.PCM_SUFFIX}"
    path.write_bytes(b"\0" * size)
    (folder / f"{name}{cache.LOUDNESS_SUFFIX}").write_text("{}", encoding="utf-8")
    when = path.stat().st_mtime - age_s
    os.utime(path, (when, when))
    return path


def test_the_cache_keeps_under_its_limit_dropping_the_least_recently_used(
    songs: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decoded song takes 23 MB a minute: without a limit the folder only grows."""
    folder = tmp_path / "memòria cau"
    folder.mkdir()
    oldest = _stale_entry(folder, "a" * 32, 2_000_000, 3_000)
    older = _stale_entry(folder, "b" * 32, 2_000_000, 2_000)
    recent = _stale_entry(folder, "c" * 32, 2_000_000, 1_000)
    monkeypatch.setattr(cache, "CACHE_LIMIT_BYTES", 6_000_000)
    decoded = cache.decoded_song(songs["440"], folder)  # 8 s: ~3 MB
    assert decoded.path.is_file()
    assert not oldest.exists() and not oldest.with_name("a" * 32 + cache.LOUDNESS_SUFFIX).exists()
    assert not older.exists()
    assert recent.exists()
    total = sum(p.stat().st_size for p in folder.iterdir() if p.suffix == cache.PCM_SUFFIX)
    assert total <= 6_000_000


def test_songs_in_use_are_never_dropped(
    songs: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "memòria cau"
    folder.mkdir()
    first = cache.decoded_song(songs["440"], folder)
    os.utime(first.path, (1_000_000_000, 1_000_000_000))  # the least recently used, but in use
    monkeypatch.setattr(cache, "CACHE_LIMIT_BYTES", 1)
    second = cache.decoded_song(songs["660"], folder)
    assert first.path.exists() and second.path.exists()
    assert first.read(0, 10).shape == (10, 2)


def test_using_a_song_again_marks_it_as_recent(songs: dict[str, Path], tmp_path: Path) -> None:
    folder = tmp_path / "memòria cau"
    folder.mkdir()
    first = cache.decoded_song(songs["440"], folder)
    os.utime(first.path, (1_000_000_000, 1_000_000_000))
    cache.decoded_song(songs["440"], folder)
    assert first.path.stat().st_mtime > 1_000_000_000
