"""C07: trim_silence (pure), ESPECIFICACIO §1.7 ter "Retallar silenci inicial i final"."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from passimaker.model import defaults
from passimaker.recorder import trim_silence
from passimaker.recorder.silence import dbfs_to_amplitude

RATE = 1000


def _audio(silence_before: int, sound: int, silence_after: int, channels: int = 2) -> np.ndarray:
    samples = np.zeros((silence_before + sound + silence_after, channels), dtype=np.float32)
    samples[silence_before : silence_before + sound, 0] = 0.5
    return samples


def test_keeps_the_margin_around_the_sound() -> None:
    assert trim_silence(_audio(2000, 3000, 1500), RATE, margin_s=0.2) == pytest.approx((1.8, 5.2))


def test_the_margin_stays_inside_the_recording() -> None:
    assert trim_silence(_audio(100, 500, 50), RATE, margin_s=0.2) == pytest.approx((0.0, 0.65))


def test_only_silence_or_nothing_gives_none() -> None:
    assert trim_silence(_audio(1000, 0, 0), RATE) is None
    assert trim_silence(np.zeros((0, 2), dtype=np.float32), RATE) is None


def test_the_threshold_uses_the_loudest_channel_and_counts_negative_samples() -> None:
    samples = np.zeros((RATE, 2), dtype=np.float32)
    samples[500, 1] = -dbfs_to_amplitude(defaults.RECORD_TRIM_THRESHOLD_DBFS)
    assert trim_silence(samples, RATE, margin_s=0.0) == pytest.approx((0.5, 0.501))
    samples[500, 1] *= 0.9  # just below -50 dBFS
    assert trim_silence(samples, RATE, margin_s=0.0) is None


def test_accepts_an_envelope_of_wave_columns() -> None:
    envelope = np.zeros(defaults.RECORD_PEAK_COLUMNS_PER_S * 10, dtype=np.float32)
    envelope[100:200] = 0.3
    assert trim_silence(envelope, defaults.RECORD_PEAK_COLUMNS_PER_S) == pytest.approx((1.8, 4.2))


def test_rejects_wrong_arguments() -> None:
    with pytest.raises(ValueError):
        trim_silence(_audio(0, 10, 0), 0)
    with pytest.raises(ValueError):
        trim_silence(_audio(0, 10, 0), RATE, margin_s=-0.1)


@given(
    before=st.integers(0, 3000),
    sound=st.integers(1, 3000),
    after=st.integers(0, 3000),
    margin=st.floats(0.0, 2.0),
)
def test_never_cuts_the_sound_and_stays_inside(before: int, sound: int, after: int, margin: float) -> None:
    samples = _audio(before, sound, after)
    result = trim_silence(samples, RATE, margin_s=margin)
    assert result is not None
    start, end = result
    assert 0.0 <= start <= before / RATE + 1e-9
    assert (before + sound) / RATE - 1e-9 <= end <= samples.shape[0] / RATE
    assert start == pytest.approx(max(0.0, before / RATE - margin))
