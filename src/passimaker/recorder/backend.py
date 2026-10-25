"""The capture backend: the only part that talks to the sound system (technology chosen in block C08).

Recorder and Monitor read from a CaptureStream in their capture thread, so the backend only has
to deliver blocks; the tests use a fake one (tests/fakes, block C09) with tones and silences.
"""

from __future__ import annotations

from typing import Protocol

from passimaker.recorder.types import AudioFrames, AudioSource


class CaptureStream(Protocol):
    """An open source. Used from a single thread (the capture thread)."""

    @property
    def sample_rate(self) -> int: ...

    @property
    def channels(self) -> int:
        """Channels of the blocks it returns: 1 or 2 (the backend mixes 5.1 and others down to stereo)."""
        ...

    def read(self, timeout_s: float) -> AudioFrames | None:
        """The next block, shape (frames, channels); None if nothing arrived within `timeout_s`.

        Raises RecorderDeviceLostError if the device was disconnected or replaced and
        RecorderDeviceError for any other failure. Silence (nothing playing) is a block of zeros
        (or, with WASAPI loopback, possibly no block at all: the caller then fills it with zeros).
        """
        ...

    def dropped_frames(self) -> int:
        """Frames lost so far because the reader was late (for the log; C08 measures it)."""
        ...

    def close(self) -> None: ...


class CaptureBackend(Protocol):
    def list_sources(self) -> tuple[AudioSource, ...]:
        """Every output (loopback) and input; order and default as list_sources() documents."""
        ...

    def open(self, source: AudioSource) -> CaptureStream:
        """Start capturing. RecorderNoDeviceError if it is gone, RecorderDeviceError otherwise."""
        ...
