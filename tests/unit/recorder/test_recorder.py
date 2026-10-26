"""C09: Recorder with the fake sound system (contract §16, ESPECIFICACIO §1.7 ter, decision 0013)."""

from __future__ import annotations

import errno
import math
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from passimaker import recorder
from passimaker.recorder import (
    ERROR_NO_SPACE,
    Recorder,
    RecorderDeviceError,
    RecorderDeviceLostError,
    RecorderDiskFullError,
    RecorderError,
    RecorderMaxDurationError,
    RecorderNoDeviceError,
    RecorderSilentError,
    RecorderState,
    RecordingSettings,
    StopReason,
    capture,
)
from passimaker.recorder.silence import dbfs_to_amplitude
from passimaker.recorder.wavwriter import TEMP_PREFIX, TempWav, read_frames, read_info
from tests.fakes.recorder import (
    HEADPHONES,
    MICROPHONE,
    SPEAKERS,
    SURROUND,
    ChangeDefault,
    Disconnect,
    Discontinuity,
    Fail,
    FakeCaptureBackend,
    Nothing,
    Segment,
    Silence,
    Tone,
    wait_for,
)

TARGET = dbfs_to_amplitude(-1.0)
SETTINGS = RecordingSettings(silence_stop=False)


def _recorder(
    tmp_path: Path,
    *script: Segment,
    settings: RecordingSettings = SETTINGS,
    source: recorder.AudioSource = SPEAKERS,
    **fake: Any,
) -> tuple[Recorder, FakeCaptureBackend]:
    backend = FakeCaptureBackend(script=script, **fake)
    return Recorder(source, tmp_path, settings, backend=backend), backend


def _record(
    tmp_path: Path, *script: Segment, settings: RecordingSettings = SETTINGS
) -> recorder.RecordingResult:
    """Plays `script`, waits until it is over and presses [■ Atura]."""
    rec, backend = _recorder(tmp_path, *script, settings=settings)
    rec.start()
    wait_for(backend.held.is_set)
    return rec.stop()


def _files(folder: Path) -> list[Path]:
    return sorted(folder.iterdir())


def _peak(path: Path) -> float:
    return float(np.abs(read_frames(path)).max())


# --- saving ---------------------------------------------------------------------------------------------


def test_records_waits_for_the_sound_trims_and_normalises(tmp_path: Path) -> None:
    result = _record(tmp_path, Silence(1.0), Tone(2.0, 0.25), Silence(1.0))
    assert result.stop_reason is StopReason.USER
    assert result.duration_s == pytest.approx(2.0 + 2 * 0.2, abs=0.03)
    assert result.trimmed_end_s == pytest.approx(0.8, abs=0.03)
    assert 0 <= result.trimmed_start_s <= 0.1  # "Comença quan soni" saved only the margin before it
    assert result.gain_db == pytest.approx(20 * math.log10(TARGET / 0.25), abs=0.01)
    assert _files(tmp_path) == [result.wav_path]
    assert result.wav_path.name.startswith(TEMP_PREFIX) and result.wav_path.suffix == ".wav"
    rate, channels, frames = read_info(result.wav_path)
    assert (rate, channels) == (48000, 2) and frames == pytest.approx(result.duration_s * rate, abs=1)
    assert _peak(result.wav_path) == pytest.approx(TARGET, rel=1e-5)
    assert _peak(result.wav_path) <= np.float32(TARGET)


def test_without_start_when_sound_the_leading_silence_is_recorded_and_trimmed(tmp_path: Path) -> None:
    settings = RecordingSettings(start_when_sound=False, silence_stop=False)
    result = _record(tmp_path, Silence(1.0), Tone(1.0, 0.5), Silence(0.5), settings=settings)
    assert result.trimmed_start_s == pytest.approx(0.8, abs=0.03)
    assert result.trimmed_end_s == pytest.approx(0.3, abs=0.03)
    assert result.duration_s == pytest.approx(1.4, abs=0.03)


def test_trimming_off_keeps_everything(tmp_path: Path) -> None:
    settings = RecordingSettings(start_when_sound=False, silence_stop=False, trim=False)
    result = _record(tmp_path, Silence(1.0), Tone(1.0, 0.5), Silence(0.5), settings=settings)
    assert (result.trimmed_start_s, result.trimmed_end_s) == (0.0, 0.0)
    assert result.duration_s == pytest.approx(2.5)


def test_normalisation_off_keeps_the_level(tmp_path: Path) -> None:
    settings = RecordingSettings(silence_stop=False, normalize=False)
    result = _record(tmp_path, Tone(1.0, 0.25), settings=settings)
    assert result.gain_db == 0.0
    assert _peak(result.wav_path) == pytest.approx(0.25, rel=1e-6)


def test_a_loud_recording_is_never_lowered(tmp_path: Path) -> None:
    settings = RecordingSettings(start_when_sound=False, silence_stop=False, trim=False)
    result = _record(tmp_path, Tone(1.0, 0.99), settings=settings)
    assert result.gain_db == 0.0
    assert _peak(result.wav_path) == pytest.approx(0.99, rel=1e-6)
    assert _files(tmp_path) == [result.wav_path]  # nothing to trim or raise: the same WAV


def test_the_quietest_channel_does_not_decide_the_gain(tmp_path: Path) -> None:
    result = _record(tmp_path, Tone(1.0, (0.4, 0.1)))
    samples = read_frames(result.wav_path)
    assert float(np.abs(samples[:, 0]).max()) == pytest.approx(TARGET, rel=1e-5)
    assert float(np.abs(samples[:, 1]).max()) == pytest.approx(TARGET / 4, rel=1e-4)


def test_the_automatic_stop_for_silence_saves_the_recording(tmp_path: Path) -> None:
    settings = RecordingSettings(silence_stop_s=1.0)
    rec, backend = _recorder(tmp_path, Tone(2.0), Silence(3.0), settings=settings)
    rec.start()
    wait_for(lambda: rec.state is RecorderState.FINISHED)
    assert not backend.held.is_set()  # stopped on its own, before the end of the script
    assert backend.closed == 1  # the source is closed at once
    result = rec.stop()
    assert result.stop_reason is StopReason.SILENCE
    assert result.duration_s == pytest.approx(2.2, abs=0.03)
    assert rec.state is RecorderState.CLOSED


def test_the_automatic_stop_waits_for_some_sound_first(tmp_path: Path) -> None:
    settings = RecordingSettings(start_when_sound=False, silence_stop_s=1.0)
    rec, backend = _recorder(tmp_path, Silence(3.0), settings=settings)
    rec.start()
    wait_for(backend.held.is_set)
    assert rec.state is RecorderState.RECORDING
    with pytest.raises(RecorderSilentError):
        rec.stop()
    assert _files(tmp_path) == []


def test_short_pauses_do_not_stop_it(tmp_path: Path) -> None:
    settings = RecordingSettings(silence_stop_s=1.0)
    result = _record(tmp_path, Tone(1.0), Silence(0.9), Tone(1.0), settings=settings)
    assert result.stop_reason is StopReason.USER
    assert result.duration_s == pytest.approx(2.9, abs=0.03)


def test_stopping_while_waiting_is_silent_and_leaves_nothing(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Silence(2.0))
    rec.start()
    wait_for(backend.held.is_set)
    assert rec.state is RecorderState.WAITING and rec.elapsed_s == 0
    with pytest.raises(RecorderSilentError) as caught:
        rec.stop()
    assert caught.value.message_key == recorder.ERROR_SILENT
    assert _files(tmp_path) == [] and rec.state is RecorderState.CLOSED


def test_sound_below_the_threshold_is_silence(tmp_path: Path) -> None:
    settings = RecordingSettings(start_when_sound=False, silence_stop=False)
    with pytest.raises(RecorderSilentError):
        _record(tmp_path, Tone(1.0, dbfs_to_amplitude(-60.0)), settings=settings)
    assert _files(tmp_path) == []


def test_discontinuities_and_empty_reads_do_not_stop_anything(tmp_path: Path) -> None:
    result = _record(tmp_path, Tone(1.0), Discontinuity(), Nothing(3), Tone(1.0), Discontinuity())
    assert result.duration_s == pytest.approx(2.0, abs=0.03)


def test_records_a_44_1_khz_output(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0), source=HEADPHONES, sample_rate=44100)
    backend.default_output = HEADPHONES.id
    rec.start()
    wait_for(backend.held.is_set)
    result = rec.stop()
    assert read_info(result.wav_path)[0] == 44100
    assert result.duration_s == pytest.approx(1.0, abs=0.03)


def test_a_mono_input_is_recorded_in_mono(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0), source=MICROPHONE)
    rec.start()
    assert len(rec.level_dbfs) == 1
    wait_for(backend.held.is_set)
    assert read_info(rec.stop().wav_path)[1] == 1


def test_a_surround_output_is_recorded_in_stereo(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0), source=SURROUND, stream_channels=6)
    backend.default_output = SURROUND.id
    rec.start()
    wait_for(backend.held.is_set)
    assert read_info(rec.stop().wav_path)[1] == 2


def test_the_source_is_used_only_from_the_capture_thread(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(0.5))
    rec.start()
    wait_for(backend.held.is_set)
    rec.stop()
    (stream,) = backend.streams
    assert stream.thread is not threading.main_thread() and stream.closed
    assert backend.closed == 1


# --- interruptions (decision 0013, G1 and G5) ----------------------------------------------------------


def _interrupted(rec: Recorder, folder: Path) -> RecorderError:
    """Waits for INTERRUPTED, checking that the WAV was gone before the error was visible."""

    def check() -> bool:
        if rec.state is RecorderState.INTERRUPTED:
            assert _files(folder) == [], "the WAV must be deleted before the error is visible"
            return True
        return False

    wait_for(check)
    error = rec.error
    assert error is not None
    with pytest.raises(type(error)) as caught:
        rec.stop()
    assert caught.value is error
    assert rec.state is RecorderState.CLOSED and _files(folder) == []
    return error


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ((Tone(1.0), Disconnect()), RecorderDeviceLostError),
        ((Tone(1.0), ChangeDefault(HEADPHONES.id), Tone(2.0)), RecorderDeviceLostError),
        ((Tone(1.0), ChangeDefault(None), Tone(2.0)), RecorderDeviceLostError),
        ((Tone(1.0), Fail(RuntimeError("Error 0x88890004"))), RecorderDeviceError),
        ((Tone(1.0), Fail(OSError(errno.EIO, "I/O"))), RecorderDeviceError),
        ((Tone(1.0), Fail(RecorderDeviceError("x"))), RecorderDeviceError),
    ],
    ids=["disconnected", "default-changed", "no-default", "error", "os-error", "device-error"],
)
def test_every_interruption_deletes_the_recording(
    tmp_path: Path, script: tuple[Segment, ...], expected: type[RecorderError]
) -> None:
    rec, _ = _recorder(tmp_path, *script)
    rec.start()
    assert isinstance(_interrupted(rec, tmp_path), expected)


def test_an_interruption_while_waiting_also_deletes(tmp_path: Path) -> None:
    rec, _ = _recorder(tmp_path, Silence(0.5), Disconnect())
    rec.start()
    assert isinstance(_interrupted(rec, tmp_path), RecorderDeviceLostError)


def test_the_maximum_duration_discards_the_recording(tmp_path: Path) -> None:
    settings = RecordingSettings(silence_stop=False, max_duration_s=1.0)
    rec, _ = _recorder(tmp_path, Tone(3.0), settings=settings)
    rec.start()
    error = _interrupted(rec, tmp_path)
    assert isinstance(error, RecorderMaxDurationError)
    assert error.message_key == recorder.ERROR_MAX_DURATION


def test_waiting_does_not_count_towards_the_maximum(tmp_path: Path) -> None:
    settings = RecordingSettings(silence_stop=False, max_duration_s=1.0)
    result = _record(tmp_path, Silence(3.0), Tone(0.5), settings=settings)
    assert result.duration_s == pytest.approx(0.7, abs=0.03)


def test_running_out_of_space_discards_the_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    space = iter([100 * 1024**3, 100 * 1024**3])  # start() and the first check; then the disk is full
    monkeypatch.setattr(capture, "free_bytes", lambda folder: next(space, 1024))
    rec, _ = _recorder(tmp_path, Tone(5.0))
    rec.start()
    error = _interrupted(rec, tmp_path)
    assert isinstance(error, RecorderDiskFullError) and error.message_key == recorder.ERROR_DISK_FULL


def test_a_full_disk_while_writing_discards_the_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = TempWav.write

    def write(self: TempWav, block: np.ndarray) -> None:
        if self.frames > 48000:
            raise OSError(errno.ENOSPC, "No space left on device")
        original(self, block)

    monkeypatch.setattr(TempWav, "write", write)
    rec, _ = _recorder(tmp_path, Tone(3.0))
    rec.start()
    assert isinstance(_interrupted(rec, tmp_path), RecorderDiskFullError)


def test_too_little_space_refuses_to_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "free_bytes", lambda folder: 1024**3 - 1)
    rec, backend = _recorder(tmp_path, Tone(1.0), settings=RecordingSettings())
    with pytest.raises(RecorderDiskFullError) as caught:
        rec.start()
    assert caught.value.message_key == ERROR_NO_SPACE
    assert backend.streams == [] and _files(tmp_path) == [] and rec.state is RecorderState.CLOSED


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RecorderNoDeviceError("gone"), RecorderNoDeviceError),
        (recorder.RecorderMicrophoneDeniedError("Error 0x80070005"), recorder.RecorderMicrophoneDeniedError),
        (RuntimeError("Error 0x8889000a"), RecorderDeviceError),
    ],
)
def test_a_source_that_cannot_be_opened(
    tmp_path: Path, error: Exception, expected: type[RecorderError]
) -> None:
    rec, _ = _recorder(tmp_path, Tone(1.0), open_error=error)
    with pytest.raises(expected):
        rec.start()
    assert rec.state is RecorderState.CLOSED and _files(tmp_path) == []


def test_another_output_than_the_default_ignores_the_default_changing(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0), ChangeDefault(SPEAKERS.id), Tone(1.5), source=HEADPHONES)
    rec.start()
    wait_for(backend.held.is_set)
    assert rec.stop().duration_s == pytest.approx(2.5, abs=0.03)


def test_an_input_ignores_the_default_output_changing(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0), ChangeDefault(HEADPHONES.id), Tone(1.5), source=MICROPHONE)
    rec.start()
    wait_for(backend.held.is_set)
    assert rec.stop().duration_s == pytest.approx(2.5, abs=0.03)
    assert backend.default_queries == 0


def test_the_default_output_is_checked_every_second(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(5.0))
    rec.start()
    wait_for(backend.held.is_set)
    rec.stop()
    assert backend.default_queries == 1 + 5  # when opening, then once per second of audio


# --- discard, states and misuse --------------------------------------------------------------------------


def test_discard_while_recording_deletes_everything(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(2.0))
    rec.start()
    wait_for(backend.held.is_set)
    assert len(_files(tmp_path)) == 1
    rec.discard()
    assert _files(tmp_path) == [] and rec.state is RecorderState.CLOSED and backend.closed == 1
    rec.discard()  # again: nothing to do
    with pytest.raises(RuntimeError):
        rec.stop()


def test_discard_after_the_automatic_stop_deletes_it(tmp_path: Path) -> None:
    rec, _ = _recorder(tmp_path, Tone(1.0), Silence(2.0), settings=RecordingSettings(silence_stop_s=1.0))
    rec.start()
    wait_for(lambda: rec.state is RecorderState.FINISHED)
    rec.discard()
    assert _files(tmp_path) == []


def test_discard_after_an_interruption(tmp_path: Path) -> None:
    rec, _ = _recorder(tmp_path, Tone(1.0), Disconnect())
    rec.start()
    wait_for(lambda: rec.state is RecorderState.INTERRUPTED)
    rec.discard()
    assert rec.state is RecorderState.CLOSED and _files(tmp_path) == []


def test_start_and_stop_only_once(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0))
    with pytest.raises(RuntimeError):
        rec.stop()
    rec.start()
    with pytest.raises(RuntimeError):
        rec.start()
    wait_for(backend.held.is_set)
    result = rec.stop()
    with pytest.raises(RuntimeError):
        rec.stop()
    with pytest.raises(RuntimeError):
        rec.start()
    assert _files(tmp_path) == [result.wav_path]  # discard() after stop() leaves the result alone
    rec.discard()
    assert _files(tmp_path) == [result.wav_path]


def test_the_temporary_folder_is_created(tmp_path: Path) -> None:
    folder = tmp_path / "temp" / "PassiMaker"
    rec, backend = _recorder(folder, Tone(1.0))
    rec.start()
    wait_for(backend.held.is_set)
    assert rec.stop().wav_path.parent == folder


# --- waves, level and time -------------------------------------------------------------------------------


def test_waves_level_and_elapsed_time_while_recording(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Silence(1.0), Tone(2.0, (0.5, 0.25)))
    rec.start()
    wait_for(backend.held.is_set)
    columns, index = rec.peaks_since(0)
    assert columns.shape == (150, 2, 2) and index == 150  # 3 s at 50 columns per second, waiting included
    assert columns.dtype == np.float32
    assert np.all(columns[:50] == 0)
    assert columns[60, 0, 1] == pytest.approx(0.5, abs=0.01) and columns[60, 1, 0] == pytest.approx(
        -0.25, abs=0.01
    )
    more, again = rec.peaks_since(index)
    assert more.shape[0] == 0 and again == index
    assert rec.level_dbfs == pytest.approx((-6.02, -12.04), abs=0.05)
    assert rec.elapsed_s == pytest.approx(2.2, abs=0.06)
    overview = rec.overview(40)
    assert overview.shape == (40, 2, 2)
    assert float(overview[:, 0, 1].max()) == pytest.approx(0.5, abs=1e-6)
    rec.stop()
    assert rec.overview(40).shape == (40, 2, 2)  # still there after stopping


def test_the_live_waves_keep_the_last_ten_seconds(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(12.0))
    rec.start()
    wait_for(backend.held.is_set)
    columns, index = rec.peaks_since(0)
    assert index == 600 and columns.shape[0] == 500
    rec.discard()


def test_the_overview_covers_the_whole_recording(tmp_path: Path) -> None:
    rec, backend = _recorder(tmp_path, Tone(1.0, 0.1), Tone(1.0, 0.8), Tone(10.0, 0.2))
    rec.start()
    wait_for(backend.held.is_set)
    result = rec.stop()
    assert result.duration_s == pytest.approx(12.0, abs=0.03)
    overview = rec.overview(10)
    assert float(overview[0, 0, 1]) == pytest.approx(0.8, abs=1e-6)  # the loud second, in the first pixel
    assert float(overview[-1, 0, 1]) == pytest.approx(0.2, abs=1e-3)
    assert rec.overview(10_000).shape == (10_000, 2, 2)
    with pytest.raises(ValueError):
        rec.overview(0)


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    sound_s=st.integers(1, 20).map(lambda n: n / 10),
    silence_tenths=st.integers(0, 30),
    stop_s=st.sampled_from([1.0, 2.0]),
)
def test_the_automatic_stop_after_exactly_that_much_silence(
    tmp_path_factory: pytest.TempPathFactory, sound_s: float, silence_tenths: int, stop_s: float
) -> None:
    folder = tmp_path_factory.mktemp("silence")
    silence_s = silence_tenths / 10
    rec, backend = _recorder(
        folder, Tone(sound_s), Silence(silence_s), settings=RecordingSettings(silence_stop_s=stop_s)
    )
    rec.start()
    wait_for(lambda: backend.held.is_set() or rec.state is RecorderState.FINISHED)
    finished = rec.state is RecorderState.FINISHED
    assert finished == (silence_s >= stop_s)
    result = rec.stop()
    assert result.stop_reason is (StopReason.SILENCE if finished else StopReason.USER)
    assert result.duration_s == pytest.approx(sound_s + min(0.2, silence_s), abs=0.03)
