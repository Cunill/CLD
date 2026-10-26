"""C09: normalisation on saving, never above -1 dBFS (user's decision of 26/10/2026)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from passimaker.recorder import Recorder, RecordingSettings
from passimaker.recorder.silence import amplitude_to_dbfs, dbfs_to_amplitude, normalize_gain
from passimaker.recorder.wavwriter import read_frames
from tests.fakes.recorder import SPEAKERS, FakeCaptureBackend, Silence, Tone, wait_for

TARGET = np.float32(dbfs_to_amplitude(-1.0))


@given(peak=st.one_of(st.just(0.0), st.floats(2**-20, 4, width=32)), target=st.floats(-40, 0))
def test_the_gain_never_goes_over_the_target_and_never_lowers(peak: float, target: float) -> None:
    gain = normalize_gain(peak, target)
    goal = np.float32(dbfs_to_amplitude(target))
    assert gain >= 1.0
    if peak >= goal or peak == 0:
        assert gain == 1.0
    else:
        raised = np.float32(peak) * np.float32(gain)
        assert raised <= goal
        assert raised == pytest.approx(float(goal), rel=1e-5)


def test_levels_in_dbfs() -> None:
    assert amplitude_to_dbfs(1.0) == 0 and amplitude_to_dbfs(0.0) == -math.inf
    assert amplitude_to_dbfs(0.5) == pytest.approx(-6.0206)
    assert normalize_gain(0.5) == pytest.approx(float(TARGET) / 0.5, rel=1e-6)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    level=st.floats(-45, 0),
    right=st.floats(0, 1),
    before=st.floats(0, 1.5),
    sound=st.floats(0.1, 2),
    after=st.floats(0, 1.5),
)
def test_a_saved_recording_never_peaks_over_minus_1_dbfs(
    tmp_path_factory: pytest.TempPathFactory,
    level: float,
    right: float,
    before: float,
    sound: float,
    after: float,
) -> None:
    folder = tmp_path_factory.mktemp("normalise")
    amplitude = dbfs_to_amplitude(level)
    script = (Silence(before), Tone(sound, (amplitude, amplitude * right)), Silence(after))
    backend = FakeCaptureBackend(script=script)
    rec = Recorder(SPEAKERS, folder, RecordingSettings(silence_stop=False), backend=backend)
    rec.start()
    wait_for(backend.held.is_set)
    result = rec.stop()
    samples = read_frames(result.wav_path)
    peak = np.float32(np.abs(samples).max())
    assert peak <= max(TARGET, np.float32(amplitude))  # a loud recording is never lowered
    expected = max(float(TARGET), amplitude)  # raised to the target, or left as it was
    assert float(peak) == pytest.approx(expected, rel=1e-5)
    # The trimmed part holds the whole sound with its margins, within the recording.
    assert result.duration_s == pytest.approx(sound + min(0.2, before) + min(0.2, after), abs=0.06)


def test_a_vanishing_peak_does_not_overflow() -> None:
    gain = normalize_gain(1e-44)
    assert math.isfinite(gain) and np.float32(1e-44) * np.float32(gain) <= TARGET
