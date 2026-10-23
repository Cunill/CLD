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
    output.close()
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


def test_pausing_and_jumping_keep_the_same_stream_open() -> None:
    """Reopening the stream makes Bluetooth headphones fade in again (M04)."""
    streams = Streams()
    output = SoundDeviceOutput(streams)
    output.start(ToneAudioSource(60.0), 0.0)
    output.start(ToneAudioSource(60.0), 30.0)  # a jump while playing
    output.stop()  # pause
    output.start(ToneAudioSource(60.0), 12.0)  # play again
    assert len(streams.opened) == 1
    assert not streams.opened[0].closed
    output.close()
    output.close()  # twice is harmless
    assert streams.opened[0].closed


def test_after_a_jump_the_card_gets_the_mix_from_the_new_instant() -> None:
    streams = Streams()
    output = SoundDeviceOutput(streams)
    output.start(ToneAudioSource(60.0), 0.0)
    stream = streams.opened[0]
    stream.pull()
    clock = output.start(ToneAudioSource(60.0), 30.0)
    stream.played.clear()
    for _ in range(5):
        stream.pull()
        time.sleep(0.005)
    expected = ToneAudioSource(60.0).read(30.0, 5 * AUDIO_BLOCK_FRAMES)
    np.testing.assert_array_equal(np.concatenate(stream.played), expected)
    stream.time = LATENCY_S + 0.01  # 10 ms after the first block of the jump is heard
    assert clock.now() == pytest.approx(30.01)
    output.close()


def test_while_paused_the_card_gets_silence_and_the_stream_closes_later() -> None:
    streams = Streams()
    output = SoundDeviceOutput(streams, keep_open_s=0.2)
    output.start(ToneAudioSource(60.0), 0.0)
    stream = streams.opened[0]
    output.stop()
    stream.played.clear()
    for _ in range(3):
        stream.pull()
    assert not np.concatenate(stream.played).any()
    assert output.underruns == 0  # silence while paused is not a missed block
    assert output.stream_open
    deadline = time.perf_counter() + 2.0
    while output.stream_open and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert stream.closed
    output.start(ToneAudioSource(60.0), 5.0)  # playing again opens a new one
    assert len(streams.opened) == 2 and streams.opened[1].started
    output.close()


def test_playing_again_before_the_delay_keeps_the_stream() -> None:
    streams = Streams()
    output = SoundDeviceOutput(streams, keep_open_s=0.2)
    output.start(ToneAudioSource(60.0), 0.0)
    output.stop()
    output.start(ToneAudioSource(60.0), 1.0)
    time.sleep(0.4)
    assert output.stream_open and not streams.opened[0].closed
    output.close()


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
    output.close()
    silent = [block for block in stream.played if not block.any()]
    assert len(silent) == output.underruns
