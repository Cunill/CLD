"""§1.7 fades: song fades, final fade when the music is longer, silence when it is shorter."""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np

from tests.audio.conftest import SR, Mixer, db, level, project, read_wav, song

WINDOW = 240  # 5 ms


def window_levels(signal: np.ndarray, frequency: float, start: int, end: int) -> list[float]:
    return [db(level(signal, frequency, n, WINDOW)) for n in range(start, end - WINDOW + 1, WINDOW)]


def test_fade_in_and_fade_out(songs: dict[str, Path], mixer: Mixer) -> None:
    mix = mixer(project(12.0, [song(songs, "440", fades=(1.0, 3.0))]))
    out = mix.read(0.0, 9 * SR)
    nominal = db(level(out, 440, 3 * SR, SR))
    fade_in = [v - nominal for v in window_levels(out, 440, 0, SR)]
    assert fade_in[0] <= -60
    assert abs(fade_in[-1]) <= 0.5
    assert all(b > a for a, b in itertools.pairwise(fade_in))
    fade_out = [v - nominal for v in window_levels(out, 440, 5 * SR, 8 * SR)]
    assert abs(fade_out[0]) <= 0.5
    assert fade_out[-1] <= -60
    assert all(b < a for a, b in itertools.pairwise(fade_out))


def test_fades_follow_a_logarithmic_curve(songs: dict[str, Path], mixer: Mixer) -> None:
    """Halfway through a fade-in the level is −30 dB: the curve is a straight line in dB."""
    mix = mixer(project(12.0, [song(songs, "440", fades=(2.0, None))]))
    out = mix.read(0.0, 4 * SR)
    nominal = db(level(out, 440, 3 * SR, SR // 2))
    assert abs(db(level(out, 440, SR - WINDOW // 2, WINDOW)) - nominal + 30) <= 0.5


def test_music_longer_than_the_show_fades_out_at_the_end(
    songs: dict[str, Path], mixer: Mixer, tmp_path: Path
) -> None:
    p = project(6.0, [song(songs, "880")])
    mix = mixer(p)
    assert mix.duration_s == 6.0
    out = mix.read(0.0, 6 * SR)
    nominal = db(level(out, 880, SR, SR))
    assert db(level(out, 880, 6 * SR - WINDOW, WINDOW)) - nominal <= -60
    assert abs(db(level(out, 880, 3 * SR - WINDOW, WINDOW)) - nominal) <= 0.5  # final fade starts at 3 s
    final = window_levels(out, 880, 3 * SR, 6 * SR)
    assert all(b < a for a, b in itertools.pairwise(final))
    mix.render_wav(tmp_path / "llarga.wav")
    wav = read_wav(tmp_path / "llarga.wav")
    assert len(wav) == 6 * SR
    assert np.abs(wav[-WINDOW:]).max() <= 10 ** ((nominal - 60) / 20)


def test_music_shorter_than_the_show_is_followed_by_absolute_silence(
    songs: dict[str, Path], mixer: Mixer, tmp_path: Path
) -> None:
    mix = mixer(project(10.0, [song(songs, "660")]))
    out = mix.read(0.0, 10 * SR)
    assert np.any(out[: 6 * SR] != 0)
    assert np.all(out[6 * SR :] == 0)
    mix.render_wav(tmp_path / "curta.wav")
    wav = read_wav(tmp_path / "curta.wav")
    assert len(wav) == 10 * SR
    assert np.all(wav[6 * SR :] == 0)


def test_disabled_fades_still_have_the_anti_click_fade(songs: dict[str, Path], mixer: Mixer) -> None:
    out = mixer(project(10.0, [song(songs, "660")])).read(0.0, 7 * SR)
    assert np.all(out[0] == 0)
    nominal = level(out, 660, SR, SR)
    assert level(out, 660, 0, 240) < 0.5 * nominal  # rising over the first 10 ms
    assert abs(db(level(out, 660, 480, 480)) - db(nominal)) <= 0.1  # nominal right after
    assert abs(db(level(out, 660, 6 * SR - 960, 480)) - db(nominal)) <= 0.1
