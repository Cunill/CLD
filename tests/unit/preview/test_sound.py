"""B13 · The real sound output, with a simulated stream (there is no sound card in the cloud).

The stream calls back like PortAudio does; the tests check the samples handed to the card are
the mix from the right instant, and that the clock follows the sample being heard.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from passimaker.audio import SAMPLE_RATE
from passimaker.preview import SoundDeviceOutput, StreamClock
from passimaker.preview.params import AUDIO_BLOCK_FRAMES
from passimaker.preview.sound import StreamCallback
from tests.fakes.audio import ToneAudioSource

BLOCK_S = AUDIO_BLOCK_FRAMES / SAMPLE_RATE
LATENCY_S = 0.1


class FakeStream:
    """A sound card driven by the test: `pull()` asks for one block, `time` is set by hand."""

    def __init__(self, callback: StreamCallback, fail: bool = False) -> None:
        self.callback = callback
        self.fail = fail
        self.time = 0.0
        self.started = self.stopped = self.closed = False
        self.played: list[np.ndarray] = []

    def start(self) -> None:
        if self.fail:
            raise OSError("cap dispositiu")
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def pull(self) -> None:
        out = np.zeros((AUDIO_BLOCK_FRAMES, 2), dtype=np.float32)
        # Blocks are heard one after the other, the first one after the output latency.
        info: Any = SimpleNamespace(outputBufferDacTime=LATENCY_S + len(self.played) * BLOCK_S)
        self.callback(out, AUDIO_BLOCK_FRAMES, info, None)
        self.played.append(out)


class Streams:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.opened: list[FakeStream] = []

    def __call__(self, callback: StreamCallback) -> FakeStream:
        stream = FakeStream(callback, self.fail)
        self.opened.append(stream)
        return stream


def test_the_card_gets_the_mix_from_the_start_instant() -> None:
    streams = Streams()
    output = SoundDeviceOutput(streams)
    source = ToneAudioSource(60.0)
    output.start(source, 10.0)
    stream = streams.opened[0]
    assert stream.started
    for _ in range(20):
        stream.pull()
        time.sleep(0.005)  # a real card asks every 21 ms: the feeder has time to read ahead
    output.stop()
    expected = ToneAudioSource(60.0).read(10.0, 20 * AUDIO_BLOCK_FRAMES)
    np.testing.assert_array_equal(np.concatenate(stream.played), expected)
    assert stream.stopped and stream.closed
    assert output.underruns == 0


def test_the_clock_follows_the_sample_being_heard() -> None:
    streams = Streams()
    output = SoundDeviceOutput(streams)
    clock = output.start(ToneAudioSource(60.0), 10.0)
    stream = streams.opened[0]
    assert clock.now() == 10.0  # nothing heard yet
    stream.pull()  # first block, heard at stream time 0.1
    stream.time = 0.05
    assert clock.now() == 10.0  # still in the output latency
    stream.time = LATENCY_S + 0.01
    assert clock.now() == pytest.approx(10.01)
    stream.pull()
    stream.time = LATENCY_S + BLOCK_S + 0.005
    assert clock.now() == pytest.approx(10.0 + BLOCK_S + 0.005)
    # Never past the sound handed to the card, and never backwards.
    stream.time = 5.0
    assert clock.now() == pytest.approx(10.0 + 2 * BLOCK_S)
    stream.time = 0.0
    assert clock.now() == pytest.approx(10.0 + 2 * BLOCK_S)
    output.stop()


def test_restarting_closes_the_previous_stream() -> None:
    streams = Streams()
    output = SoundDeviceOutput(streams)
    output.start(ToneAudioSource(60.0), 0.0)
    output.start(ToneAudioSource(60.0), 30.0)
    assert streams.opened[0].closed
    assert not streams.opened[1].closed
    output.stop()
    output.stop()  # twice is harmless
    assert streams.opened[1].closed


def test_a_device_that_cannot_start_raises_and_leaves_nothing_open() -> None:
    streams = Streams(fail=True)
    output = SoundDeviceOutput(streams)
    with pytest.raises(OSError):
        output.start(ToneAudioSource(60.0), 0.0)
    assert streams.opened[0].closed


def test_an_empty_queue_plays_silence_without_moving_the_clock() -> None:
    clock = StreamClock(lambda: 0.0, 3.0)
    assert clock.now() == 3.0
    streams = Streams()
    output = SoundDeviceOutput(streams)
    output.start(ToneAudioSource(60.0), 0.0)
    stream = streams.opened[0]
    # Drain faster than the feeder thread can possibly refill: some blocks may be silence.
    deadline = time.perf_counter() + 0.5
    while output.underruns == 0 and time.perf_counter() < deadline:
        stream.pull()
    output.stop()
    silent = [block for block in stream.played if not block.any()]
    assert len(silent) == output.underruns
