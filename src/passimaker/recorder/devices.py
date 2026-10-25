"""The list of sources the user can record from (block C09 implements it)."""

from __future__ import annotations

from passimaker.recorder.backend import CaptureBackend
from passimaker.recorder.types import AudioSource

_NOT_IMPLEMENTED = "passimaker.recorder: implemented in block C09"


def list_sources(*, backend: CaptureBackend | None = None) -> tuple[AudioSource, ...]:
    """First the outputs (loopback), the default one first; then the inputs (decision 0013, G6).

    An empty tuple when there is no sound device at all (the interface shows ERROR_NO_DEVICE).
    """
    raise NotImplementedError(_NOT_IMPLEMENTED)
