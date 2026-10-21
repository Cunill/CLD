"""Fixtures of the FFmpeg bridge tests: signals that make cut errors measurable."""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from tests.fixtures.generate import find_ffmpeg

NOISE_SECONDS = 4.0
NOISE_RATE = 48000
NOISE_AMPLITUDE = 0.3

_ENCODERS: dict[str, list[str]] = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
}
LOSSY = ("mp3", "m4a", "ogg")


def noise(seconds: float, rate: int, channels: int, seed: int = 7) -> NDArray[np.float64]:
    """Low-pass filtered white noise: no period, so a cross-correlation finds one single offset."""
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((round(seconds * rate), channels))
    kernel = np.ones(8) / 8
    smooth = np.stack([np.convolve(raw[:, c], kernel, mode="same") for c in range(channels)], axis=1)
    return NOISE_AMPLITUDE * smooth / np.abs(smooth).max()


def write_wav(samples: NDArray[np.float64], rate: int, dest: Path) -> None:
    ints = np.round(np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(samples.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(ints.tobytes())


def encode(src: Path, dest: Path, fmt: str, extra: list[str] | None = None) -> Path:
    cmd = [find_ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src)]
    cmd += [*(extra or []), *_ENCODERS[fmt], str(dest)]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


@pytest.fixture(scope="session")
def noise_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The same stereo noise in WAV, MP3, M4A, FLAC and OGG (48 kHz)."""
    folder = tmp_path_factory.mktemp("soroll")
    wav = folder / "soroll.wav"
    write_wav(noise(NOISE_SECONDS, NOISE_RATE, 2), NOISE_RATE, wav)
    files = {"wav": wav}
    for fmt in _ENCODERS:
        files[fmt] = encode(wav, folder / f"soroll.{fmt}", fmt)
    return files


@pytest.fixture(scope="session")
def mono_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("mono") / "mono.wav"
    write_wav(noise(2.0, NOISE_RATE, 1, seed=3), NOISE_RATE, path)
    return path


@pytest.fixture(scope="session")
def wav_44k(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("cd") / "cd 44,1 kHz.wav"
    write_wav(noise(3.0, 44100, 2, seed=5), 44100, path)
    return path


@pytest.fixture(scope="session")
def photo_jpg(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A plain JPEG (own file, so these tests do not depend on the photo fixtures of block B4)."""
    path = tmp_path_factory.mktemp("foto") / "foto.jpg"
    Image.new("RGB", (320, 240), (120, 140, 160)).save(path, quality=90)
    return path


def read_pcm(path: Path) -> NDArray[np.float32]:
    return np.fromfile(path, dtype="<f4").reshape(-1, 2)


def cut_error(signal: NDArray[np.floating], reference: NDArray[np.floating], start: int, max_lag: int) -> int:
    """How many samples `signal` starts after reference[start] (best cross-correlation)."""
    m = min(len(signal), len(reference) - start - max_lag) - 1
    lags = range(max(-max_lag, -start), max_lag + 1)
    scores = [float(np.dot(signal[:m], reference[start + lag : start + lag + m])) for lag in lags]
    return list(lags)[int(np.argmax(scores))]
