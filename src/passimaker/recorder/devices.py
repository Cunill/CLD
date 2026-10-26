"""The list of sources the user can record from (decision 0013, G6)."""

from __future__ import annotations

from passimaker.recorder.backend import CaptureBackend, SoundcardBackend
from passimaker.recorder.types import AudioSource, SourceKind


def list_sources(*, backend: CaptureBackend | None = None) -> tuple[AudioSource, ...]:
    """First the outputs (loopback), the default one first; then the inputs, the default one first.

    An empty tuple when there is no sound device at all (the interface shows ERROR_NO_DEVICE).
    RecorderDeviceError if the sound system cannot be read. Takes a moment: not on the UI thread.
    """
    sources = (backend or default_backend()).list_sources()
    return tuple(sorted(sources, key=lambda s: (s.kind is not SourceKind.OUTPUT_LOOPBACK, not s.is_default)))


def default_backend() -> CaptureBackend:
    return SoundcardBackend()
