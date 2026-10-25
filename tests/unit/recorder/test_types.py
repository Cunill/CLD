"""C07: types, errors, message keys and defaults of the recorder (contract §16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from passimaker import recorder
from passimaker.common import PassiMakerError
from passimaker.i18n import MESSAGES, message
from passimaker.model import defaults
from passimaker.recorder import types


def _source(
    channels: int = 2, kind: recorder.SourceKind = recorder.SourceKind.OUTPUT_LOOPBACK
) -> recorder.AudioSource:
    return recorder.AudioSource(
        id="0", name="Altaveus (Realtek)", kind=kind, is_default=True, sample_rate=48000, channels=channels
    )


def test_every_error_key_has_a_catalan_message() -> None:
    keys = {v for name, v in vars(types).items() if name.startswith("ERROR_") and isinstance(v, str)}
    assert len(keys) == 7
    for key in keys:
        assert key.startswith("recorder.") and key in MESSAGES
        assert message(key) != key


def test_errors_carry_their_key_and_derive_from_the_base_error() -> None:
    errors = [
        (recorder.RecorderNoDeviceError(), recorder.ERROR_NO_DEVICE),
        (recorder.RecorderDeviceLostError(), recorder.ERROR_DEVICE_LOST),
        (recorder.RecorderSilentError(), recorder.ERROR_SILENT),
        (recorder.RecorderDiskFullError(), recorder.ERROR_DISK_FULL),
        (recorder.RecorderDiskFullError(recorder.ERROR_NO_SPACE), recorder.ERROR_NO_SPACE),
        (recorder.RecorderMaxDurationError(), recorder.ERROR_MAX_DURATION),
        (recorder.RecorderDeviceError("PortAudio error -9999"), recorder.ERROR_DEVICE),
    ]
    for error, key in errors:
        assert isinstance(error, recorder.RecorderError) and isinstance(error, PassiMakerError)
        assert error.message_key == key


def test_the_messages_match_the_defaults() -> None:
    assert defaults.RECORD_MAX_DURATION_S == 30 * 60
    assert "30 minuts" in message(recorder.ERROR_MAX_DURATION)
    assert defaults.RECORD_MIN_FREE_BYTES == 1024**3
    assert "1 GB" in message(recorder.ERROR_NO_SPACE)


def test_defaults_of_the_specification() -> None:
    assert defaults.RECORD_START_WHEN_SOUND and defaults.RECORD_START_THRESHOLD_DBFS == -50
    assert defaults.RECORD_SILENCE_STOP_ENABLED and defaults.RECORD_SILENCE_STOP_S == 5
    assert (defaults.RECORD_SILENCE_STOP_RANGE.minimum, defaults.RECORD_SILENCE_STOP_RANGE.maximum) == (1, 60)
    assert defaults.RECORD_TRIM_ENABLED and defaults.RECORD_TRIM_THRESHOLD_DBFS == -50
    assert pytest.approx(0.2) == defaults.RECORD_TRIM_MARGIN_S
    assert defaults.RECORD_MAX_WARNING_S == 60
    assert defaults.RECORD_MP3_BITRATE_KBPS == 192
    assert defaults.RECORD_WAVE_WINDOW_S == 10
    assert defaults.RECORD_PEAK_COLUMNS_PER_S == 50
    # §1.7 ter: 30 min are 90,000 columns per channel, under 1 MB as float32 min and max.
    columns = defaults.RECORD_MAX_DURATION_S * defaults.RECORD_PEAK_COLUMNS_PER_S
    assert columns == 90_000 and columns * 2 * 4 < 1024**2


def test_settings_default_to_the_defaults() -> None:
    settings = recorder.RecordingSettings()
    assert settings.start_when_sound == defaults.RECORD_START_WHEN_SOUND
    assert settings.silence_stop_s == defaults.RECORD_SILENCE_STOP_S
    assert settings.max_duration_s == defaults.RECORD_MAX_DURATION_S
    assert settings.min_free_bytes == defaults.RECORD_MIN_FREE_BYTES


def test_recorded_channels_are_one_or_two() -> None:
    assert _source(1).recorded_channels == 1
    assert _source(2).recorded_channels == 2
    assert _source(6).recorded_channels == 2


def test_the_enumerations_of_the_contract() -> None:
    assert {k.name for k in recorder.SourceKind} == {"OUTPUT_LOOPBACK", "INPUT"}
    assert {r.name for r in recorder.StopReason} == {"USER", "SILENCE"}


def test_recording_result_has_the_fields_of_the_contract(tmp_path: Path) -> None:
    result = recorder.RecordingResult(
        wav_path=tmp_path / "a.wav",
        duration_s=180.0,
        trimmed_start_s=1.5,
        trimmed_end_s=0.0,
        stop_reason=recorder.StopReason.SILENCE,
    )
    assert result.stop_reason is recorder.StopReason.SILENCE


def test_the_unimplemented_parts_say_so(tmp_path: Path) -> None:
    source = _source()
    rec = recorder.Recorder(source, tmp_path)
    assert rec.settings == recorder.RecordingSettings() and rec.source is source
    monitor = recorder.Monitor(source)
    calls = [
        recorder.list_sources,
        lambda: recorder.remove_leftovers(tmp_path),
        rec.start,
        rec.stop,
        rec.discard,
        lambda: rec.state,
        lambda: rec.error,
        lambda: rec.elapsed_s,
        lambda: rec.level_dbfs,
        lambda: rec.peaks_since(0),
        lambda: rec.overview(800),
        monitor.start,
        monitor.stop,
        lambda: monitor.level_dbfs,
        lambda: monitor.peaks_since(0),
        lambda: monitor.error,
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="C09"):
            call()
    assert list(tmp_path.iterdir()) == []
