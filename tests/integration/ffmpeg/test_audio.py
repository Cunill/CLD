"""B7: probe, decode_audio, measure_loudness and waveform with the real FFmpeg."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

from passimaker import ffmpeg
from tests.fixtures.generate import (
    AUDIO_FORMATS,
    TONE_AMPLITUDE,
    TONE_SPECS,
    ToneSpec,
    find_ffmpeg,
    tone_samples,
)
from tests.integration.ffmpeg.conftest import (
    LOSSY,
    NOISE_RATE,
    NOISE_SECONDS,
    cut_error,
    noise,
    read_pcm,
    write_wav,
)

MS = NOISE_RATE // 1000  # samples per millisecond at 48 kHz

TONE_CASES = [(spec, fmt) for spec in TONE_SPECS for fmt in AUDIO_FORMATS]


@pytest.mark.parametrize(("spec", "fmt"), TONE_CASES, ids=[f"{s.name}.{f}" for s, f in TONE_CASES])
def test_probe_reads_duration_rate_and_channels(
    fixture_files: dict[str, Path], spec: ToneSpec, fmt: str
) -> None:
    info = ffmpeg.probe(fixture_files[f"{spec.name}.{fmt}"])
    assert abs(info.duration_s - spec.duration_s) <= 0.010
    assert info.has_audio
    assert info.sample_rate == 48000
    assert info.channels == 2
    assert not info.has_video
    assert info.width is None and info.height is None


def test_probe_duration_matches_what_decode_audio_produces(
    noise_files: dict[str, Path], tmp_path: Path
) -> None:
    for fmt, path in noise_files.items():
        info = ffmpeg.probe(path)
        pcm = ffmpeg.decode_audio(path, tmp_path / f"{fmt}.pcm")
        assert abs(pcm.frames / ffmpeg.AUDIO_SAMPLE_RATE - info.duration_s) <= 0.001, fmt


def test_cover_art_is_not_video(fixture_files: dict[str, Path], photo_jpg: Path, tmp_path: Path) -> None:
    song = tmp_path / "amb portada.mp3"
    cmd = [find_ffmpeg(), "-nostdin", "-loglevel", "error", "-y", "-i", str(fixture_files["tone_440.wav"])]
    cmd += ["-i", str(photo_jpg), "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame"]
    cmd += ["-c:v", "copy", "-disposition:v", "attached_pic", str(song)]
    subprocess.run(cmd, check=True, capture_output=True)
    info = ffmpeg.probe(song)
    assert info.has_audio
    assert not info.has_video
    assert abs(info.duration_s - 8.0) <= 0.010


def test_wav_decodes_bit_exact(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    spec = TONE_SPECS[0]
    pcm = ffmpeg.decode_audio(fixture_files[f"{spec.name}.wav"], tmp_path / "out.f32")
    expected = tone_samples(spec).astype(np.float32) / 32768
    assert pcm.frames == len(expected)
    assert pcm.path == tmp_path / "out.f32"
    np.testing.assert_allclose(read_pcm(pcm.path), expected, atol=1e-6)


@pytest.mark.parametrize("fmt", ["wav", "mp3", "m4a", "flac", "ogg"])
@pytest.mark.parametrize(("start_s", "end_s"), [(0.0, None), (1.2345, 3.0), (0.0107, 0.5003), (2.5, None)])
def test_decode_cuts_within_one_millisecond(
    noise_files: dict[str, Path], tmp_path: Path, fmt: str, start_s: float, end_s: float | None
) -> None:
    pcm = ffmpeg.decode_audio(noise_files[fmt], tmp_path / "tros.f32", start_s, end_s)
    # Both ends are rounded to whole samples.
    expected_frames = round((end_s if end_s is not None else NOISE_SECONDS) * NOISE_RATE) - round(
        start_s * NOISE_RATE
    )
    assert abs(pcm.frames - expected_frames) <= MS
    decoded = read_pcm(pcm.path)
    reference = noise(NOISE_SECONDS, NOISE_RATE, 2)
    start = round(start_s * NOISE_RATE)
    for channel in (0, 1):
        error = cut_error(decoded[:, channel], reference[:, channel], start, max_lag=10 * MS)
        assert abs(error) <= MS, f"{fmt}: el tall comença {error} mostres desplaçat"
    if fmt not in LOSSY:
        assert pcm.frames == expected_frames


def test_decode_resamples_to_48k(wav_44k: Path, tmp_path: Path) -> None:
    pcm = ffmpeg.decode_audio(wav_44k, tmp_path / "48k.f32", 1.0, 2.0)
    assert pcm.frames == 48000
    full = ffmpeg.decode_audio(wav_44k, tmp_path / "tot.f32")
    assert abs(full.frames - 3 * 48000) <= 1


def test_mono_is_played_on_both_sides_at_full_level(mono_wav: Path, tmp_path: Path) -> None:
    decoded = read_pcm(ffmpeg.decode_audio(mono_wav, tmp_path / "m.f32").path)
    reference = noise(2.0, NOISE_RATE, 1, seed=3)[:, 0]
    np.testing.assert_array_equal(decoded[:, 0], decoded[:, 1])
    np.testing.assert_allclose(decoded[:, 0], reference, atol=1 / 16384)


def test_cut_outside_the_file_gives_no_frames(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    pcm = ffmpeg.decode_audio(fixture_files["tone_660.flac"], tmp_path / "buit.f32", 7.0, 9.0)
    assert pcm.frames == 0
    pcm = ffmpeg.decode_audio(fixture_files["tone_660.flac"], tmp_path / "final.f32", 5.0, 9.0)
    assert pcm.frames == 48000


@pytest.mark.parametrize("fmt", AUDIO_FORMATS)
def test_loudness_of_a_minus_12_dbfs_tone(fixture_files: dict[str, Path], fmt: str) -> None:
    loudness = ffmpeg.measure_loudness(fixture_files[f"tone_440.{fmt}"])
    peak_dbfs = 20 * math.log10(TONE_AMPLITUDE)
    # Stereo sine: mean square A²/2 per channel, two channels summed, K-weighting ≈ -0.3 dB at 440 Hz.
    expected_lufs = -0.691 + 10 * math.log10(2 * TONE_AMPLITUDE**2 / 2) - 0.3
    assert abs(loudness.integrated_lufs - expected_lufs) <= 0.5
    assert abs(loudness.true_peak_dbfs - peak_dbfs) <= 0.5


def test_mono_loudness_counts_both_sides(tmp_path: Path) -> None:
    mono = noise(3.0, NOISE_RATE, 1, seed=11)
    write_wav(mono, NOISE_RATE, tmp_path / "mono.wav")
    write_wav(np.repeat(mono, 2, axis=1), NOISE_RATE, tmp_path / "estereo.wav")
    a = ffmpeg.measure_loudness(tmp_path / "mono.wav")
    b = ffmpeg.measure_loudness(tmp_path / "estereo.wav")
    assert abs(a.integrated_lufs - b.integrated_lufs) <= 0.1
    assert abs(a.true_peak_dbfs - b.true_peak_dbfs) <= 0.1


def test_loudness_of_silence(tmp_path: Path) -> None:
    write_wav(np.zeros((NOISE_RATE * 2, 2)), NOISE_RATE, tmp_path / "silenci.wav")
    loudness = ffmpeg.measure_loudness(tmp_path / "silenci.wav")
    assert loudness.integrated_lufs <= -70
    assert loudness.true_peak_dbfs == -math.inf


def test_waveform_of_a_tone(fixture_files: dict[str, Path]) -> None:
    peaks = ffmpeg.waveform(fixture_files["tone_880.m4a"], 200)
    assert peaks.shape == (200,)
    assert peaks.dtype == np.float32
    assert np.all(np.abs(peaks - TONE_AMPLITUDE) <= 0.03)


def test_waveform_follows_the_signal_in_time(tmp_path: Path) -> None:
    samples = np.zeros((NOISE_RATE * 4, 2))
    samples[NOISE_RATE * 2 :, 1] = 0.8  # silence, then a loud right channel
    samples[NOISE_RATE * 2 :: 2, 1] *= -1
    write_wav(samples, NOISE_RATE, tmp_path / "meitat.wav")
    peaks = ffmpeg.waveform(tmp_path / "meitat.wav", 40)
    assert np.all(peaks[:19] == 0)
    assert np.all(np.abs(peaks[21:] - 0.8) <= 0.01)
    assert np.all((peaks >= 0) & (peaks <= 1))


@pytest.mark.parametrize("points", [1, 7, 2000, 200_000])
def test_waveform_has_the_requested_number_of_points(fixture_files: dict[str, Path], points: int) -> None:
    peaks = ffmpeg.waveform(fixture_files["tone_660.ogg"], points)
    assert peaks.shape == (points,)
    if points <= 2000:  # each bucket holds at least one period of the tone
        assert np.all(peaks > 0.2)
    else:  # fewer than 2 samples per bucket: still peaks of the signal
        assert np.all((peaks >= 0) & (peaks <= TONE_AMPLITUDE + 0.03))


def test_waveform_needs_at_least_one_point(fixture_files: dict[str, Path]) -> None:
    with pytest.raises(ValueError):
        ffmpeg.waveform(fixture_files["tone_660.ogg"], 0)
