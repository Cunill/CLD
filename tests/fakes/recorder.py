"""Replacement for the sound system (contract §16): scripted tones and silences, no sound card.

FakeCaptureBackend implements passimaker.recorder.CaptureBackend. Every stream it opens plays
`script`, a list of segments, in blocks of `block_s` and as fast as it is read (no real time):
Tone and Silence deliver audio; Nothing makes read() return None; Discontinuity counts one;
ChangeDefault replaces the default output (what WASAPI does without an error, block C08);
Disconnect and Fail make read() raise. When the script is over the stream holds (read() returns
None until the capture ends), so a test decides when to stop; `held` tells it has got there.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

import numpy as np

from passimaker.recorder import AudioSource, RecorderDeviceLostError, SourceKind
from passimaker.recorder.types import AudioFrames

RATE = 48000
SPEAKERS = AudioSource(
    id="{speakers}", name="Altaveus (Realtek)", kind=SourceKind.OUTPUT_LOOPBACK, is_default=True,
    sample_rate=48000, channels=2,
)  # fmt: skip
HEADPHONES = AudioSource(
    id="{bt}", name="Auriculars X-SMC01", kind=SourceKind.OUTPUT_LOOPBACK, is_default=False,
    sample_rate=44100, channels=2,
)  # fmt: skip
SURROUND = AudioSource(
    id="{hdmi}", name="Televisor (HDMI)", kind=SourceKind.OUTPUT_LOOPBACK, is_default=False,
    sample_rate=48000, channels=6,
)  # fmt: skip
MICROPHONE = AudioSource(
    id="{mic}", name="Micròfon (Webcam C170)", kind=SourceKind.INPUT, is_default=True,
    sample_rate=48000, channels=1,
)  # fmt: skip


def dbfs(level: float) -> float:
    return float(10.0 ** (level / 20.0))


@dataclass(frozen=True)
class Tone:
    seconds: float
    amplitude: float | tuple[float, ...] = 0.5
    """Peak of the sine, the same for every channel or one per channel."""
    frequency: float = 440.0


@dataclass(frozen=True)
class Silence:
    seconds: float


@dataclass(frozen=True)
class Nothing:
    reads: int = 1
    """read() returns None this many times."""


@dataclass(frozen=True)
class Discontinuity:
    pass


@dataclass(frozen=True)
class ChangeDefault:
    output_id: str | None


@dataclass(frozen=True)
class Disconnect:
    pass


@dataclass(frozen=True)
class Fail:
    error: BaseException


type Segment = Tone | Silence | Nothing | Discontinuity | ChangeDefault | Disconnect | Fail


class FakeStream:
    def __init__(self, backend: FakeCaptureBackend, source: AudioSource) -> None:
        self._backend = backend
        self._source = source
        self._events = backend.events_for(source)
        self._discontinuities = 0
        self.thread = threading.current_thread()
        self.closed = False
        self.frames_delivered = 0

    @property
    def sample_rate(self) -> int:
        return self._backend.sample_rate

    @property
    def channels(self) -> int:
        return self._backend.stream_channels or self._source.recorded_channels

    def read(self, timeout_s: float) -> AudioFrames | None:
        assert threading.current_thread() is self.thread, "read from another thread"
        assert not self.closed
        while True:
            event = next(self._events, None)
            if event is None:
                self._backend.held.set()
                self._backend.wake.wait(min(timeout_s, 0.01))
                return None
            if isinstance(event, np.ndarray):
                self.frames_delivered += event.shape[0]
                return event
            if isinstance(event, Nothing):
                return None
            if isinstance(event, Discontinuity):
                self._discontinuities += 1
            elif isinstance(event, ChangeDefault):
                self._backend.default_output = event.output_id
            elif isinstance(event, Disconnect):
                raise RecorderDeviceLostError("fake: disconnected")
            elif isinstance(event, Fail):
                raise event.error

    def discontinuities(self) -> int:
        return self._discontinuities

    def close(self) -> None:
        assert threading.current_thread() is self.thread, "closed from another thread"
        self.closed = True
        self._backend.closed += 1


@dataclass
class FakeCaptureBackend:
    sources: Sequence[AudioSource] = (SPEAKERS, HEADPHONES, MICROPHONE)
    script: Sequence[Segment] = ()
    sample_rate: int = RATE
    block_s: float = 0.05
    default_output: str | None = SPEAKERS.id
    open_error: BaseException | None = None
    list_error: BaseException | None = None
    stream_channels: int | None = None
    """Channels of the delivered blocks; None: the source's recorded channels."""
    streams: list[FakeStream] = field(default_factory=list[FakeStream])
    closed: int = 0
    default_queries: int = 0
    held: threading.Event = field(default_factory=threading.Event)
    wake: threading.Event = field(default_factory=threading.Event)

    def list_sources(self) -> tuple[AudioSource, ...]:
        if self.list_error is not None:
            raise self.list_error
        return tuple(self.sources)

    def open(self, source: AudioSource) -> FakeStream:
        if self.open_error is not None:
            raise self.open_error
        stream = FakeStream(self, source)
        self.streams.append(stream)
        return stream

    def default_output_id(self) -> str | None:
        self.default_queries += 1
        return self.default_output

    def events_for(self, source: AudioSource) -> Iterator[AudioFrames | Segment]:
        block = max(1, round(self.block_s * self.sample_rate))
        channels = self.stream_channels or source.recorded_channels
        position = 0
        for segment in self.script:
            if isinstance(segment, Tone | Silence):
                frames = round(segment.seconds * self.sample_rate)
                for first in range(0, frames, block):
                    count = min(block, frames - first)
                    yield _render(segment, position, count, channels, self.sample_rate, first == 0)
                    position += count
            else:
                yield segment


def _render(
    segment: Tone | Silence, position: int, count: int, channels: int, rate: int, starts: bool
) -> AudioFrames:
    if isinstance(segment, Silence):
        return np.zeros((count, channels), dtype=np.float32)
    amplitudes = (
        segment.amplitude if isinstance(segment.amplitude, tuple) else (segment.amplitude,) * channels
    )
    t = (position + np.arange(count)) / rate
    wave = np.sin(2 * math.pi * segment.frequency * t)
    # The first sample of the tone is at its peak: what the tests compare against is exact.
    if starts:
        wave[0] = 1.0
    return np.stack([wave * a for a in amplitudes[:channels]], axis=1).astype(np.float32)


def tone_seconds(*segments: Segment) -> float:
    """Seconds of audio in `segments`."""
    return sum(s.seconds for s in segments if isinstance(s, Tone | Silence))


def wait_for(condition: Callable[[], bool], timeout_s: float = 10.0) -> None:
    """Until `condition()` is true (the capture thread runs on its own); fails after `timeout_s`."""
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("the condition did not become true in time")
        time.sleep(0.002)
