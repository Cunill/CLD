"""M9 · Audio engine: sequential mix with trims, fades, volumes and normalisation (block B8)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from passi.common import AudioBlock, CancelToken, ProgressCallback
from passi.model.types import Project
from passi.timeline import AudioPlan

SAMPLE_RATE = 48000
CHANNELS = 2


class AudioSource(Protocol):
    @property
    def duration_s(self) -> float: ...

    def read(self, t_s: float, frames: int) -> AudioBlock:
        """Mixed audio from t_s; zero-padded past the end. Fast enough for real time."""
        ...

    def render_wav(
        self, dest: Path, progress: ProgressCallback | None = None, cancel: CancelToken | None = None
    ) -> None:
        """Writes the whole mix (duration of the show) as 16-bit PCM WAV, block by block."""
        ...


def prepare(project: Project, plan: AudioPlan, cache_dir: Path) -> AudioSource:
    """Decodes each song once into cache_dir (via passi.ffmpeg) and returns the mixer."""
    raise NotImplementedError("B8")
