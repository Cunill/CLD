"""Mixer on raw PCM files: placement, trims, gains, random access, WAV output, cancellation."""

from __future__ import annotations

import errno
import wave
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from passimaker.audio import AudioSource, Track
from passimaker.common import CancelToken
from passimaker.timeline import Interval
from tests.unit.audio.helpers import SR, pcm_song, segment, source, tone


def read_wav(path: Path) -> NDArray[np.int16]:
    with wave.open(str(path), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, SR)
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2)


def test_mixed_source_implements_the_audio_source_contract(tmp_path: Path) -> None:
    contract: AudioSource = source([], {}, total_s=1.0)
    assert contract.duration_s == 1.0


def test_segments_play_their_source_at_the_planned_frames(tmp_path: Path) -> None:
    ramp = np.repeat((np.arange(SR * 3) / (SR * 10))[:, None], 2, axis=1).astype(np.float32)
    tracks = {"a": Track(pcm_song(tmp_path, "a", ramp), 1.0)}
    mix = source([segment("a", 0.5, 1.5, source=1.0)], tracks, total_s=2.0)
    out = mix.read(0.0, 2 * SR)
    assert np.all(out[: SR // 2] == 0)
    assert np.all(out[SR + SR // 2 :] == 0)
    np.testing.assert_array_equal(out[SR // 2 : SR + SR // 2], ramp[SR : 2 * SR])


def test_song_gain_scales_the_samples(tmp_path: Path) -> None:
    samples = tone(440, 1.0, 0.2)
    tracks = {"a": Track(pcm_song(tmp_path, "a", samples), 0.5)}
    out = source([segment("a", 0.0, 1.0)], tracks, total_s=1.0, master=0.5).read(0.0, SR)
    np.testing.assert_allclose(out, samples * 0.25, atol=1e-7)


def test_reading_outside_the_mix_gives_zeros(tmp_path: Path) -> None:
    tracks = {"a": Track(pcm_song(tmp_path, "a", tone(440, 2.0)), 1.0)}
    mix = source([segment("a", 0.0, 2.0)], tracks, total_s=1.0)
    assert mix.duration_s == 1.0
    before = mix.read(-1.0, SR // 2)
    after = mix.read(1.0, SR)
    assert before.shape == (SR // 2, 2) and np.all(before == 0)
    assert np.all(after == 0)
    straddle = mix.read(-0.5, SR)
    assert np.all(straddle[: SR // 2] == 0) and np.any(straddle[SR // 2 :] != 0)
    assert mix.read(0.3, 0).shape == (0, 2)


def test_a_song_shorter_than_its_segment_is_padded_with_silence(tmp_path: Path) -> None:
    tracks = {"a": Track(pcm_song(tmp_path, "a", tone(440, 0.5)), 1.0)}
    out = source([segment("a", 0.0, 1.0)], tracks, total_s=1.0).read(0.0, SR)
    assert np.all(out[SR // 2 :] == 0)


def test_songs_without_track_stay_silent(tmp_path: Path) -> None:
    tracks = {"a": Track(pcm_song(tmp_path, "a", tone(440, 1.0)), 1.0)}
    mix = source([segment("lost", 0.0, 1.0), segment("a", 1.0, 2.0)], tracks, total_s=2.0)
    out = mix.read(0.0, 2 * SR)
    assert np.all(out[:SR] == 0) and np.any(out[SR:] != 0)


def loud_mix(tmp_path: Path):
    rng = np.random.default_rng(3)
    a = (rng.standard_normal((3 * SR, 2)) * 0.4).astype(np.float32)
    b = tone(660, 3.0, 0.9)
    tracks = {"a": Track(pcm_song(tmp_path, "a", a), 1.4), "b": Track(pcm_song(tmp_path, "b", b), 1.3)}
    segments = [segment("a", 0.0, 2.5, 0.2, 0.5, 0.01), segment("b", 2.5, 5.0, 0.0, 0.01, 1.0)]
    return source(segments, tracks, total_s=4.8, master=0.9, final_fade=Interval(1.8, 4.8))


def test_peaks_never_exceed_minus_1_dbfs(tmp_path: Path) -> None:
    out = loud_mix(tmp_path).read(0.0, 5 * SR)
    assert np.abs(out).max() <= 10 ** (-1 / 20)


def test_any_read_equals_the_same_frames_of_a_whole_read(tmp_path: Path) -> None:
    mix = loud_mix(tmp_path)
    whole = mix.read(0.0, mix.total_frames)
    for first in (0, 1, 1000, 47_999, 120_000, 230_000):
        for count in (1, 512, 4096, 48_000):
            block = mix.read(first / SR, count)
            expected = whole[first : first + count]
            np.testing.assert_allclose(block[: len(expected)], expected, rtol=0, atol=1e-6)


def test_render_wav_writes_the_same_mix_at_16_bits(tmp_path: Path) -> None:
    mix = loud_mix(tmp_path)
    calls: list[tuple[int, int]] = []
    dest = tmp_path / "mescla é.wav"
    mix.render_wav(dest, lambda done, total: calls.append((done, total)))
    pcm = read_wav(dest)
    assert len(pcm) == mix.total_frames
    expected = np.round(mix.read(0.0, mix.total_frames) * 32767)
    assert np.abs(pcm.astype(np.float64) - expected).max() <= 1
    assert calls[-1] == (mix.total_frames, mix.total_frames)
    assert [done for done, _ in calls] == sorted(done for done, _ in calls)


def test_render_wav_is_deterministic(tmp_path: Path) -> None:
    mix = loud_mix(tmp_path)
    mix.render_wav(tmp_path / "1.wav")
    mix.render_wav(tmp_path / "2.wav")
    assert (tmp_path / "1.wav").read_bytes() == (tmp_path / "2.wav").read_bytes()


def test_cancel_stops_and_deletes_the_partial_wav(tmp_path: Path) -> None:
    tracks = {"a": Track(pcm_song(tmp_path, "a", tone(440, 20.0)), 1.0)}
    mix = source([segment("a", 0.0, 20.0)], tracks, total_s=20.0)
    token = CancelToken()
    calls: list[int] = []

    def progress(done: int, total: int) -> None:
        calls.append(done)
        token.cancel()

    dest = tmp_path / "cancel.wav"
    mix.render_wav(dest, progress, token)
    assert len(calls) == 1
    assert not dest.exists()


def test_an_error_while_writing_deletes_the_partial_wav(tmp_path: Path) -> None:
    tracks = {"a": Track(pcm_song(tmp_path, "a", tone(440, 12.0)), 1.0)}
    mix = source([segment("a", 0.0, 12.0)], tracks, total_s=12.0)

    def progress(done: int, total: int) -> None:
        raise RuntimeError("fallada")

    dest = tmp_path / "error.wav"
    with pytest.raises(RuntimeError):
        mix.render_wav(dest, progress)
    assert not dest.exists()


@pytest.mark.skipif(not Path("/dev/full").exists(), reason="cal /dev/full (Linux)")
def test_a_full_disk_raises_enospc_and_leaves_devices_alone(tmp_path: Path) -> None:
    tracks = {"a": Track(pcm_song(tmp_path, "a", tone(440, 2.0)), 1.0)}
    with pytest.raises(OSError) as error:
        source([segment("a", 0.0, 2.0)], tracks, total_s=2.0).render_wav(Path("/dev/full"))
    assert error.value.errno == errno.ENOSPC
    assert Path("/dev/full").exists()


def test_silent_project_gives_a_silent_wav_of_the_right_length(tmp_path: Path) -> None:
    mix = source([], {}, total_s=3.5)
    mix.render_wav(tmp_path / "silenci.wav")
    pcm = read_wav(tmp_path / "silenci.wav")
    assert len(pcm) == round(3.5 * SR) and not pcm.any()


def test_empty_project_gives_an_empty_wav(tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []
    source([], {}, total_s=0.0).render_wav(tmp_path / "buit.wav", lambda d, t: calls.append((d, t)))
    assert len(read_wav(tmp_path / "buit.wav")) == 0
    assert calls == [(0, 0)]
