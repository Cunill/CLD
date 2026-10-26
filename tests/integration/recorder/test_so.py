"""C09: passimaker.recorder with the real sound card and soundcard (marker `so`).

Never on the CI nor in the cloud (no sound card there): on the user's Windows PC, with music
playing through the default output, and
    set PASSIMAKER_SO=1   (PowerShell: $env:PASSIMAKER_SO = "1")
    uv run pytest -m so
The steps, one at a time, are in docs/sessions/C09.md ("Proves al teu PC").
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from passimaker import recorder
from passimaker.recorder import Monitor, Recorder, RecordingSettings, SourceKind, list_sources
from passimaker.recorder.wavwriter import read_frames, read_info

pytestmark = [
    pytest.mark.so,
    pytest.mark.skipif(not os.environ.get("PASSIMAKER_SO"), reason="cal PASSIMAKER_SO=1 (PC de l'usuari)"),
]


def _default_output() -> recorder.AudioSource:
    sources = list_sources()
    assert sources, "no s'ha trobat cap sortida de so"
    assert sources[0].kind is SourceKind.OUTPUT_LOOPBACK and sources[0].is_default
    return sources[0]


def test_list_sources() -> None:
    sources = list_sources()
    for source in sources:
        mark = "*" if source.is_default else " "
        print(f"{source.kind.value:16} {mark} {source.name} · {source.channels} canals")
    outputs = [s for s in sources if s.kind is SourceKind.OUTPUT_LOOPBACK]
    assert outputs and outputs[0].is_default and sum(s.is_default for s in outputs) == 1
    assert sources[: len(outputs)] == tuple(outputs)  # the outputs come first


def test_monitor_shows_the_sound_without_writing() -> None:
    monitor = Monitor(_default_output())
    monitor.start()
    try:
        time.sleep(2.0)
        columns, index = monitor.peaks_since(0)
        assert monitor.error is None
        assert index >= 80 and columns.shape[1] == 2
        assert float(np.abs(columns).max()) > 0, "no arriba so: posa música a la sortida per defecte"
    finally:
        monitor.stop()


def test_record_5_seconds_of_the_default_output() -> None:
    temp = Path(tempfile.gettempdir())
    settings = RecordingSettings(start_when_sound=False, silence_stop=False, trim=False)
    rec = Recorder(_default_output(), temp, settings)
    rec.start()
    try:
        time.sleep(5.0)
        assert rec.error is None and rec.state is recorder.RecorderState.RECORDING
        assert rec.elapsed_s == pytest.approx(5.0, abs=0.5)
        result = rec.stop()
    except BaseException:
        rec.discard()
        raise
    try:
        rate, channels, frames = read_info(result.wav_path)
        assert (rate, channels) == (48000, 2)
        assert frames / rate == pytest.approx(5.0, abs=0.5)
        peak = float(np.abs(read_frames(result.wav_path)).max())
        assert peak == pytest.approx(10 ** (-1 / 20), rel=1e-3) or result.gain_db == 0.0
        print(f"Gravats {frames / rate:.2f} s, guany {result.gain_db:+.1f} dB")
    finally:
        result.wav_path.unlink(missing_ok=True)
