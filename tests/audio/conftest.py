"""Songs and measuring tools for the audio engine tests (real FFmpeg).

The songs are generated here, not in tests/fixtures/generate.py, so these tests do not depend on
the photo fixtures that other blocks may change (same approach as tests/integration/ffmpeg).
"""

from __future__ import annotations

import math
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from passimaker.audio import MixedAudioSource, prepare
from passimaker.model.types import Fade, Music, Photo, Project, Song
from passimaker.timeline import compute_timeline
from tests.fixtures.generate import find_ffmpeg

SR = 48000
NOMINAL = 0.25  # -12 dBFS, like tests/fixtures/generate.TONE_AMPLITUDE


def sine(frequency: float, seconds: float, amplitude: float = NOMINAL, rate: int = SR) -> NDArray[np.float64]:
    n = np.arange(round(seconds * rate), dtype=np.float64)
    return amplitude * np.sin(2 * math.pi * frequency * n / rate)


def write_wav(mono: NDArray[np.float64], dest: Path, rate: int = SR, channels: int = 2) -> Path:
    """The same signal on every channel, 16 bits."""
    samples = np.repeat(mono[:, None], channels, axis=1)
    ints = np.round(np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(samples.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(ints.tobytes())
    return dest


def read_wav(path: Path) -> NDArray[np.float64]:
    with wave.open(str(path), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, SR)
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2)
    return data.astype(np.float64) / 32767


@pytest.fixture(scope="session")
def songs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("cançons")
    files = {
        "440": write_wav(sine(440, 8.0), folder / "to 440.wav"),
        "660": write_wav(sine(660, 6.0), folder / "to 660.wav"),
        "880": write_wav(sine(880, 10.0), folder / "to 880.wav"),
        "660_loud": write_wav(sine(660, 5.0, 0.5), folder / "fort 660.wav"),
        "880_quiet": write_wav(sine(880, 5.0, 0.03), folder / "fluix 880.wav"),
        "step": write_wav(np.concatenate([sine(440, 2.0), sine(660, 2.0)]), folder / "esglaó.wav"),
        "mono_44k": write_wav(sine(880, 3.0, rate=44100), folder / "mono 44,1 kHz.wav", 44100, channels=1),
    }
    clicks = sine(440, 5.0, 0.02)
    clicks[:: SR // 2] = 0.9
    files["clicks"] = write_wav(clicks, folder / "cops.wav")
    mp3 = folder / "to 440.mp3"
    cmd = [find_ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(files["440"])]
    subprocess.run([*cmd, "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True, capture_output=True)
    files["mp3"] = mp3
    files["corrupt"] = folder / "malmesa.mp3"
    files["corrupt"].write_bytes(b"no soc pas una canco" * 100)
    return files


DURATIONS = {"440": 8.0, "660": 6.0, "880": 10.0, "660_loud": 5.0, "880_quiet": 5.0, "step": 4.0}
DURATIONS |= {"mono_44k": 3.0, "clicks": 5.0, "mp3": 8.0, "corrupt": 8.0}


def song(
    files: dict[str, Path],
    name: str,
    *,
    song_id: str | None = None,
    trim: tuple[float, float | None] = (0.0, None),
    fades: tuple[float | None, float | None] = (None, None),
    volume: float = 1.0,
    gain_db: float | None = None,
) -> Song:
    """A song of the test set; a fade of None is disabled (only the 10 ms anti-click fade)."""
    fade_in, fade_out = fades
    return Song(
        id=song_id or name,
        path=files[name],
        relative_path=None,
        original_duration_s=DURATIONS[name],
        trim_start_s=trim[0],
        trim_end_s=trim[1],
        fade_in=Fade(fade_in is not None, fade_in or 0.0),
        fade_out=Fade(fade_out is not None, fade_out or 0.0),
        volume=volume,
        loudness_gain_db=gain_db,
    )


def project(
    show_s: float, songs_: list[Song], *, master: float = 1.0, normalize: bool = True, photo_s: float = 2.0
) -> Project:
    count = max(1, round(show_s / photo_s))
    photos = tuple(Photo(f"p{i}", Path(f"{i}.jpg"), None, 4000, 3000) for i in range(count))
    music = Music(master_volume=master, normalize=normalize, songs=tuple(songs_))
    return Project(slides=photos, default_duration_s=photo_s, music=music)


type Mixer = Callable[[Project], MixedAudioSource]


@pytest.fixture
def mixer(tmp_path: Path) -> Mixer:
    def make(p: Project) -> MixedAudioSource:
        return prepare(p, compute_timeline(p).audio_plan, tmp_path / "memòria cau")

    return make


def level(signal: NDArray[np.floating], frequency: float, start: int, length: int) -> float:
    """Amplitude of a sine of known frequency in signal[start:start+length] (least squares; left channel)."""
    x = signal[start : start + length, 0].astype(np.float64)
    n = np.arange(start, start + length, dtype=np.float64)
    basis = np.stack(
        [np.sin(2 * math.pi * frequency * n / SR), np.cos(2 * math.pi * frequency * n / SR)], axis=1
    )
    coefficients, *_ = np.linalg.lstsq(basis, x, rcond=None)
    return float(np.hypot(*coefficients))


def db(value: float) -> float:
    return 20 * math.log10(max(value, 1e-12))


def dominant(signal: NDArray[np.floating], chunk: int, frequencies: tuple[float, ...]) -> list[float | None]:
    """The strongest of `frequencies` in each chunk (None if the chunk is silent)."""
    result: list[float | None] = []
    for start in range(0, len(signal) - chunk + 1, chunk):
        levels = [level(signal, f, start, chunk) for f in frequencies]
        best = int(np.argmax(levels))
        result.append(frequencies[best] if levels[best] > 1e-3 else None)
    return result
