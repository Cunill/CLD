"""Fade curve (§1.7): logarithmic, from silence to the nominal level."""

from __future__ import annotations

import numpy as np

from passimaker.audio.curves import fade_in_gain, fade_out_envelope, segment_envelope
from passimaker.audio.params import FADE_FLOOR_DB


def db(gain: float) -> float:
    return 20 * np.log10(gain)


def test_fade_goes_from_silence_to_nominal_and_always_rises() -> None:
    p = np.linspace(0.0, 1.0, 10001)
    gain = fade_in_gain(p)
    assert gain[0] == 0.0
    assert gain[-1] == 1.0
    assert np.all(np.diff(gain) > 0)


def test_fade_is_linear_in_db_above_the_floor() -> None:
    for p in (0.5, 0.75, 0.9, 0.99):
        expected = FADE_FLOOR_DB * (1 - p)
        assert abs(db(float(fade_in_gain(np.array([p]))[0])) - expected) < 0.3


def test_fade_start_is_below_minus_60_db() -> None:
    assert float(fade_in_gain(np.array([0.01]))[0]) < 10 ** (-60 / 20)


def test_segment_envelope_fades_in_and_out_on_exact_frames() -> None:
    env = segment_envelope(0, 1000, 0, 1000, fade_in=100, fade_out=200)
    assert env[0] == 0.0
    assert np.all(np.diff(env[:101]) > 0)
    assert np.all(env[100:800] == 1.0)
    assert np.all(np.diff(env[800:]) < 0)
    assert 0 < env[-1] < 1e-3


def test_segment_envelope_of_a_part_matches_the_whole() -> None:
    whole = segment_envelope(500, 2000, 500, 2500, fade_in=300, fade_out=400)
    part = segment_envelope(2200, 300, 500, 2500, fade_in=300, fade_out=400)
    assert np.array_equal(part, whole[1700:])


def test_final_fade_reaches_silence_at_its_end() -> None:
    env = fade_out_envelope(0, 400, 100, 300)
    assert np.all(env[:101] == 1.0)
    assert np.all(np.diff(env[100:301]) < 0)
    assert np.all(env[300:] == 0.0)
