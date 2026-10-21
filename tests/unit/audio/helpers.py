"""Mixer tests without FFmpeg: songs written straight as raw float32 PCM, like the cache does."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from passimaker.audio import DecodedSong, MixedAudioSource, Track
from passimaker.audio.mixer import place
from passimaker.timeline import AudioPlan, AudioSegment, Interval

SR = 48000


def tone(frequency: float, seconds: float, amplitude: float = 0.25) -> NDArray[np.float32]:
    n = np.arange(round(seconds * SR), dtype=np.float64)
    mono = amplitude * np.sin(2 * math.pi * frequency * n / SR)
    return np.repeat(mono[:, None], 2, axis=1).astype(np.float32)


def pcm_song(folder: Path, name: str, samples: NDArray[np.float32]) -> DecodedSong:
    path = folder / f"{name}.f32"
    samples.astype("<f4").tofile(path)
    return DecodedSong(path, len(samples))


def segment(
    song_id: str, start: float, end: float, source: float = 0.0, fade_in: float = 0.0, fade_out: float = 0.0
) -> AudioSegment:
    return AudioSegment(song_id, start, end, source, fade_in, fade_out)


def source(
    segments: list[AudioSegment],
    tracks: dict[str, Track],
    total_s: float,
    master: float = 1.0,
    final_fade: Interval | None = None,
) -> MixedAudioSource:
    plan = AudioPlan(tuple(segments), final_fade)
    fade = None if final_fade is None else (round(final_fade.start * SR), round(final_fade.end * SR))
    return MixedAudioSource(place(plan, tracks), round(total_s * SR), master, fade)
