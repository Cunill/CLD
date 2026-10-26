"""C09: a recording made with the fake sound system goes through the real FFmpeg to an MP3.

What the window (block C10) will do after [■ Atura]: the trimmed and normalised WAV becomes an MP3
of RECORD_MP3_BITRATE_KBPS with convert_to_mp3 (C04), in a free name from safe_target_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from passimaker import ffmpeg
from passimaker.common.files import safe_target_path
from passimaker.model import defaults
from passimaker.recorder import Recorder, RecordingSettings, capture
from tests.fakes.recorder import HEADPHONES, FakeCaptureBackend, Silence, Tone, wait_for


@pytest.fixture(autouse=True)
def _plenty_of_space(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "free_bytes", lambda folder: 100 * 1024**3)


def test_a_recording_becomes_an_mp3(tmp_path: Path) -> None:
    temp, music = tmp_path / "temp", tmp_path / "Música"
    music.mkdir()
    backend = FakeCaptureBackend(
        script=(Silence(1.0), Tone(3.0, 0.1), Silence(1.0)), sample_rate=44100, default_output=HEADPHONES.id
    )
    rec = Recorder(HEADPHONES, temp, RecordingSettings(silence_stop=False), backend=backend)
    rec.start()
    wait_for(backend.held.is_set)
    result = rec.stop()
    info = ffmpeg.probe(result.wav_path)
    assert info.has_audio and info.sample_rate == 44100 and info.channels == 2
    assert info.duration_s == pytest.approx(result.duration_s, abs=0.01)
    target = safe_target_path(music, "Gravació 26-10-2026 18.30", fallback="Gravació")
    assert target == music / "Gravació 26-10-2026 18.30.mp3"
    ffmpeg.convert_to_mp3(
        result.wav_path, target, defaults.RECORD_MP3_BITRATE_KBPS, ffmpeg.Mp3Tags(title=target.stem)
    )
    result.wav_path.unlink()  # the caller's (contract §16)
    mp3 = ffmpeg.probe(target)
    assert mp3.sample_rate == 48000 and mp3.channels == 2
    assert mp3.duration_s == pytest.approx(3.4, abs=0.05)
    assert list(temp.iterdir()) == []
    assert safe_target_path(music, "Gravació 26-10-2026 18.30") == music / "Gravació 26-10-2026 18.30 (2).mp3"
