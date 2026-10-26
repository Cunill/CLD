"""C09: Monitor, the waves and the level before recording, never writing to disk (contract §16)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from passimaker.recorder import (
    Monitor,
    RecorderDeviceLostError,
    RecorderNoDeviceError,
    wavwriter,
)
from passimaker.recorder import capture as capture_module
from tests.fakes.recorder import (
    HEADPHONES,
    SPEAKERS,
    ChangeDefault,
    Disconnect,
    FakeCaptureBackend,
    Silence,
    Tone,
    wait_for,
)


@pytest.fixture(autouse=True)
def _no_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the monitor must not write anything")

    monkeypatch.setattr(wavwriter, "TempWav", refuse)
    monkeypatch.setattr(capture_module, "TempWav", refuse)


def test_shows_the_waves_and_the_level_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    backend = FakeCaptureBackend(script=(Silence(1.0), Tone(1.0, (0.5, 0.125))))
    monitor = Monitor(SPEAKERS, backend=backend)
    assert monitor.source is SPEAKERS
    monitor.start()
    wait_for(backend.held.is_set)
    columns, index = monitor.peaks_since(0)
    assert columns.shape == (100, 2, 2) and index == 100
    assert np.all(columns[:50] == 0) and float(columns[60:, 0, 1].max()) == pytest.approx(0.5, abs=1e-6)
    assert monitor.level_dbfs == pytest.approx((-6.02, -18.06), abs=0.05)
    assert monitor.error is None
    monitor.stop()
    monitor.stop()  # again: nothing
    assert backend.closed == 1
    assert list(tmp_path.iterdir()) == []


def test_keeps_only_the_last_ten_seconds(tmp_path: Path) -> None:
    backend = FakeCaptureBackend(script=(Tone(11.0),))
    monitor = Monitor(SPEAKERS, backend=backend)
    monitor.start()
    wait_for(backend.held.is_set)
    columns, index = monitor.peaks_since(0)
    assert (columns.shape[0], index) == (500, 550)
    newer, _ = monitor.peaks_since(540)
    assert newer.shape[0] == 10
    monitor.stop()


def test_reports_a_lost_output(tmp_path: Path) -> None:
    backend = FakeCaptureBackend(script=(Tone(1.0), Disconnect()))
    monitor = Monitor(SPEAKERS, backend=backend)
    monitor.start()
    wait_for(lambda: monitor.error is not None)
    assert isinstance(monitor.error, RecorderDeviceLostError)
    assert backend.closed == 1
    monitor.stop()


def test_a_change_of_the_default_output_is_a_lost_output() -> None:
    backend = FakeCaptureBackend(script=(Tone(1.0), ChangeDefault(HEADPHONES.id), Tone(2.0)))
    monitor = Monitor(SPEAKERS, backend=backend)
    monitor.start()
    wait_for(lambda: monitor.error is not None)
    assert isinstance(monitor.error, RecorderDeviceLostError)


def test_cannot_open() -> None:
    monitor = Monitor(SPEAKERS, backend=FakeCaptureBackend(open_error=RecorderNoDeviceError("gone")))
    with pytest.raises(RecorderNoDeviceError):
        monitor.start()
    with pytest.raises(RuntimeError):
        monitor.start()
    monitor.stop()
