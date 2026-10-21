"""Normalisation to −16 LUFS, limiter at −1 dBFS, no clicks at the cuts, song and master volumes."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from passimaker.ffmpeg import measure_loudness
from passimaker.timeline import compute_timeline
from tests.audio.conftest import SR, Mixer, db, level, project, read_wav, song, write_wav

CEILING = 10 ** (-1 / 20)


def test_each_song_is_levelled_to_minus_16_lufs(songs: dict[str, Path], mixer: Mixer, tmp_path: Path) -> None:
    p = project(
        12.0,
        [
            song(songs, "660_loud", trim=(0.0, 4.0)),
            song(songs, "440", trim=(0.0, 4.0)),
            song(songs, "880_quiet", trim=(0.0, 4.0)),
        ],
    )
    mix = mixer(p)
    assert set(mix.measured_gains_db) == {"660_loud", "440", "880_quiet"}
    mix.render_wav(tmp_path / "mescla.wav")
    wav = read_wav(tmp_path / "mescla.wav")
    assert np.abs(wav).max() <= CEILING
    for i, segment in enumerate(compute_timeline(p).audio_plan.segments):
        part = wav[round(segment.video_start * SR) + 2400 : round(segment.video_end * SR) - 2400, 0]
        loudness = measure_loudness(write_wav(part, tmp_path / f"tros {i}.wav"))
        assert abs(loudness.integrated_lufs + 16) <= 1, segment.song_id


def test_without_normalisation_songs_keep_their_level(songs: dict[str, Path], mixer: Mixer) -> None:
    p = project(12.0, [song(songs, "660_loud", trim=(0, 4)), song(songs, "880_quiet")], normalize=False)
    mix = mixer(p)
    out = mix.read(0.0, 8 * SR)
    assert mix.measured_gains_db == {}
    assert abs(db(level(out, 660, SR, SR)) - db(0.5)) <= 0.05
    assert abs(db(level(out, 880, 5 * SR, SR)) - db(0.03)) <= 0.05


def test_limiter_keeps_peaks_below_minus_1_dbfs(songs: dict[str, Path], mixer: Mixer, tmp_path: Path) -> None:
    """Quiet music with loud clicks: normalisation raises it and the clicks would pass the ceiling."""
    mix = mixer(project(6.0, [song(songs, "clicks", volume=1.5)]))
    assert mix.measured_gains_db["clicks"] > 5
    mix.render_wav(tmp_path / "cops.wav")
    wav = read_wav(tmp_path / "cops.wav")
    assert np.abs(wav).max() <= CEILING
    assert np.abs(mix.read(0.0, 6 * SR)).max() <= CEILING


def test_no_clicks_at_the_cuts(songs: dict[str, Path], mixer: Mixer, tmp_path: Path) -> None:
    """At the cuts the high-frequency energy (2nd difference) is not above that of the music."""
    p = project(8.0, [song(songs, "440", trim=(0.3, 2.77)), song(songs, "880", trim=(1.1, 3.9))])
    mix = mixer(p)
    mix.render_wav(tmp_path / "talls.wav")
    wav = read_wav(tmp_path / "talls.wav")
    curvature = np.abs(np.diff(wav[:, 0], n=2))
    steady = curvature[3 * SR : 4 * SR].max()  # inside the 880 Hz song: the sharpest music here
    for t in (0.0, 2.47, 2.47 + 2.8):
        n = round(t * SR)
        around = curvature[max(0, n - 960) : n + 960]
        assert around.max() <= 1.05 * steady, t


def test_song_volume_and_master_volume(songs: dict[str, Path], mixer: Mixer) -> None:
    def steady_db(volume: float = 1.0, master: float = 1.0) -> float:
        p = project(10.0, [song(songs, "660", volume=volume)], master=master)
        return db(level(mixer(p).read(0.0, 4 * SR), 660, 2 * SR, SR))

    reference = steady_db()
    assert abs(steady_db(volume=0.5) - reference - 20 * math.log10(0.5)) <= 0.2
    assert abs(steady_db(volume=1.5) - reference - 20 * math.log10(1.5)) <= 0.2
    assert abs(steady_db(master=0.5) - reference - 20 * math.log10(0.5)) <= 0.2
    assert abs(steady_db(volume=0.8, master=0.7) - reference - 20 * math.log10(0.56)) <= 0.2
    p = project(10.0, [song(songs, "660")], master=0.0)
    assert not mixer(p).read(0.0, 4 * SR).any()


def test_a_stored_gain_is_used_instead_of_measuring(songs: dict[str, Path], mixer: Mixer) -> None:
    measured = mixer(project(10.0, [song(songs, "660")]))
    stored = mixer(project(10.0, [song(songs, "660", gain_db=-6.0)]))
    assert stored.measured_gains_db == {}
    a = level(measured.read(0.0, 4 * SR), 660, 2 * SR, SR)
    b = level(stored.read(0.0, 4 * SR), 660, 2 * SR, SR)
    assert abs(db(b) - db(0.25) + 6.0) <= 0.05
    assert abs(db(a) - db(0.25) - measured.measured_gains_db["660"]) <= 0.05
