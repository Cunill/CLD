"""Tone AudioSource: a constant sine wave, useful to test preview and export without B8."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from passimaker.common import AudioBlock, CancelToken, ProgressCallback

SAMPLE_RATE = 48000


class ToneAudioSource:
    """Implements passimaker.audio.AudioSource."""

    def __init__(self, duration_s: float, frequency: float = 440.0, amplitude: float = 0.25) -> None:
        self._duration_s = duration_s
        self.frequency = frequency
        self.amplitude = amplitude
        self.reads: list[tuple[float, int]] = []

    @property
    def duration_s(self) -> float:
        return self._duration_s

    def read(self, t_s: float, frames: int) -> AudioBlock:
        self.reads.append((t_s, frames))
        start = round(t_s * SAMPLE_RATE)
        idx = np.arange(start, start + frames, dtype=np.float64)
        mono = self.amplitude * np.sin(2 * math.pi * self.frequency * idx / SAMPLE_RATE)
        mono[idx >= round(self._duration_s * SAMPLE_RATE)] = 0.0
        mono[idx < 0] = 0.0
        return np.repeat(mono[:, None], 2, axis=1).astype(np.float32)

    def render_wav(
        self, dest: Path, progress: ProgressCallback | None = None, cancel: CancelToken | None = None
    ) -> None:
        total = round(self._duration_s * SAMPLE_RATE)
        block = self.read(0.0, total)
        with wave.open(str(dest), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(np.round(block * 32767).astype(np.int16).tobytes())
        if progress is not None:
            progress(total, total)
