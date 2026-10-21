"""Limiter: never above the ceiling, transparent below it, and local (same result in any block)."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from passimaker.audio import limiter

CEILING = 10 ** (-1 / 20)


def naive_sliding_min(values: NDArray[np.float64], width: int) -> NDArray[np.float64]:
    return np.array([values[i : i + width].min() for i in range(len(values) - width + 1)])


@given(
    st.lists(st.floats(0, 1, allow_nan=False), min_size=1, max_size=200),
    st.integers(1, 50),
)
def test_sliding_min_matches_the_definition(values: list[float], width: int) -> None:
    array = np.array(values)
    result = limiter.sliding_min(array, width)
    if len(values) < width:
        assert len(result) == 0
    else:
        assert np.array_equal(result, naive_sliding_min(array, width))


def noisy(seed: int, frames: int, amplitude: float) -> NDArray[np.float32]:
    rng = np.random.default_rng(seed)
    signal = rng.standard_normal((frames, 2)) * amplitude / 3
    clicks = rng.integers(0, frames, size=max(1, frames // 500))
    signal[clicks] *= 8
    return signal.astype(np.float32)


@settings(max_examples=50, deadline=None)
@given(st.integers(0, 10_000), st.floats(0.05, 4.0), st.integers(1, 64), st.integers(0, 256))
def test_output_never_exceeds_the_ceiling(seed: int, amplitude: float, lookahead: int, hold: int) -> None:
    signal = noisy(seed, 4000, amplitude)
    out = limiter.limit(signal, lookahead, hold, CEILING)
    before, after = limiter.context(lookahead, hold)
    assert out.shape == (4000 - before - after, 2)
    assert np.abs(out).max() <= CEILING


def test_signal_below_the_ceiling_is_untouched() -> None:
    signal = noisy(1, 3000, 0.1)
    signal = signal * (0.8 / np.abs(signal).max())
    before, after = limiter.context(240, 2400)
    padded = np.concatenate([np.zeros((before, 2), np.float32), signal, np.zeros((after, 2), np.float32)])
    assert np.array_equal(limiter.limit(padded, 240, 2400, CEILING), signal)


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 10_000), st.integers(0, 3000), st.integers(1, 3000))
def test_any_block_equals_the_same_frames_of_the_whole(seed: int, first: int, count: int) -> None:
    lookahead, hold = 48, 120
    before, after = limiter.context(lookahead, hold)
    signal = noisy(seed, 7000, 2.0)
    whole = limiter.limit(signal, lookahead, hold, CEILING)
    count = min(count, len(whole) - first)
    if count <= 0:
        return
    block = limiter.limit(signal[first : first + before + count + after], lookahead, hold, CEILING)
    assert np.allclose(block, whole[first : first + count], rtol=0, atol=1e-6)


def test_gain_ramps_down_before_a_peak_and_recovers_after_the_hold() -> None:
    lookahead, hold = 100, 300
    before, _ = limiter.context(lookahead, hold)
    signal = np.full((3000, 2), 0.5, dtype=np.float32)
    signal[1500] = 1.8
    out = limiter.limit(signal, lookahead, hold, CEILING)
    gain = out[:, 0] / signal[before : before + len(out), 0]
    peak = 1500 - before
    assert abs(out[peak, 0]) <= CEILING
    assert np.all(gain[: peak - lookahead] == 1.0)  # untouched long before the peak
    assert np.all(np.diff(gain[peak - lookahead : peak + 1]) <= 1e-12)  # smooth descent
    assert np.allclose(gain[peak + hold + lookahead :], 1.0, rtol=0, atol=1e-6)  # released
