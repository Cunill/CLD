"""Performance of the audio engine (marker perf: run locally and at the milestones).

- Reading 1 s of audio takes less than 5 ms (preview).
- An 80-minute WAV is written in less than 60 s with less than 200 MB of memory (export).
"""

from __future__ import annotations

import statistics
import time
import tracemalloc
import wave
from pathlib import Path

import pytest

from passimaker.audio import prepare
from passimaker.model.types import Fade, Music, Photo, Project, Song
from passimaker.timeline import compute_timeline
from tests.audio.conftest import SR, Mixer, project, sine, song, write_wav

pytestmark = pytest.mark.perf

SONG_S = 300.0
SHOW_MINUTES = 80


def test_reading_one_second_takes_less_than_5_ms(songs: dict[str, Path], mixer: Mixer) -> None:
    timings: dict[str, float] = {}
    cases = {
        "tres cançons": project(
            20.0, [song(songs, "440", fades=(1.0, 3.0)), song(songs, "660"), song(songs, "880")]
        ),
        "limitador actiu": project(6.0, [song(songs, "clicks", volume=1.5)]),
    }
    for name, p in cases.items():
        mix = mixer(p)
        mix.read(0.0, SR)  # warm the file cache
        samples: list[float] = []
        for i in range(60):
            t = (i * 0.37) % (mix.duration_s - 1.0)
            start = time.perf_counter()
            mix.read(t, SR)
            samples.append(time.perf_counter() - start)
        timings[name] = statistics.median(samples) * 1000
    print("Llegir 1 s (mediana, ms):", {k: round(v, 2) for k, v in timings.items()})
    assert all(ms < 5.0 for ms in timings.values()), timings


@pytest.fixture(scope="module")
def long_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Path]:
    """80 minutes of music: one 5-minute song used 16 times (decoded once), 80 minutes of photos."""
    folder = tmp_path_factory.mktemp("llarg")
    path = write_wav(sine(440, SONG_S), folder / "cinc minuts.wav")
    count = round(SHOW_MINUTES * 60 / SONG_S)
    songs = tuple(
        Song(f"s{i}", path, None, SONG_S, fade_in=Fade(True, 1.0), fade_out=Fade(True, 3.0), volume=1.2)
        for i in range(count)
    )
    photos = tuple(Photo(f"p{i}", Path(f"{i}.jpg"), None, 4000, 3000) for i in range(SHOW_MINUTES * 20))
    p = Project(slides=photos, default_duration_s=3.0, music=Music(master_volume=0.9, songs=songs))
    return p, folder


def test_80_minute_wav_in_less_than_60_s_and_200_mb(long_project: tuple[Project, Path]) -> None:
    p, folder = long_project
    mix = prepare(p, compute_timeline(p).audio_plan, folder / "memòria cau")
    assert mix.duration_s == SHOW_MINUTES * 60
    dest = folder / "llarg.wav"
    start = time.perf_counter()
    mix.render_wav(dest)
    elapsed = time.perf_counter() - start
    with wave.open(str(dest), "rb") as w:
        assert w.getnframes() == SHOW_MINUTES * 60 * SR
    dest.unlink()
    tracemalloc.start()
    try:
        mix.render_wav(dest)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        dest.unlink(missing_ok=True)
    print(f"WAV de {SHOW_MINUTES} min: {elapsed:.1f} s, memòria màxima {peak / 2**20:.0f} MB")
    assert elapsed < 60
    assert peak < 200 * 2**20
