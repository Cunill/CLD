"""The real sound output (sounddevice / PortAudio) and the clock that follows it.

The mix is read a little ahead by a feeder thread into a queue of blocks; the sound card's
callback only takes the next block from the queue. So the callback never waits for the mixer,
and the sound does not stop when the render thread keeps the processor busy (§1.8).

The clock is the position of the sample being heard: the callback records, for each block, the
show time of its first sample and the moment (on the stream's own clock) it reaches the speakers;
now() interpolates from the last record with the stream's clock. It starts at `from_s`, stays
there until the first sample is heard (the output latency) and never goes backwards.

sounddevice is imported only when a stream is opened: a computer without PortAudio still runs the
program, with the internal clock and no sound.
"""

from __future__ import annotations

import importlib
import logging
import queue
import threading
from collections.abc import Callable
from typing import Any, Protocol, cast

import numpy as np

from passimaker.audio import CHANNELS, SAMPLE_RATE, AudioSource
from passimaker.common import AudioBlock
from passimaker.preview.params import AUDIO_BLOCK_FRAMES, AUDIO_BUFFER_BLOCKS, AUDIO_LATENCY, KEEP_OPEN_S

_log = logging.getLogger(__name__)

_FEED_TIMEOUT_S = 0.1


class AudioStream(Protocol):
    """The part of sounddevice.OutputStream the output uses."""

    @property
    def time(self) -> float: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


type StreamCallback = Callable[[np.ndarray, int, Any, Any], None]
type StreamFactory = Callable[[StreamCallback], AudioStream]
"""Opens a 48 kHz stereo float32 output stream that calls the callback for every block."""


def sounddevice_stream(callback: StreamCallback) -> AudioStream:
    """The default device, through sounddevice (raises if there is no PortAudio or no device)."""
    sounddevice: Any = importlib.import_module("sounddevice")
    stream: Any = sounddevice.OutputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=AUDIO_BLOCK_FRAMES,
        latency=AUDIO_LATENCY,
        callback=callback,
    )
    return cast(AudioStream, stream)


class _Feeder:
    """Reads the mix ahead in a thread; the callback takes blocks without waiting."""

    def __init__(self, source: AudioSource, from_s: float) -> None:
        self._source = source
        self._next_frame = round(from_s * SAMPLE_RATE)
        self._queue: queue.Queue[AudioBlock] = queue.Queue(maxsize=AUDIO_BUFFER_BLOCKS)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="passimaker-so", daemon=True)

    def prime(self) -> None:
        """Fills the queue before the stream starts, so the first callbacks have sound."""
        while not self._queue.full():
            self._queue.put_nowait(self._read())

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(1.0)

    def take(self) -> AudioBlock | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _read(self) -> AudioBlock:
        block = self._source.read(self._next_frame / SAMPLE_RATE, AUDIO_BLOCK_FRAMES)
        self._next_frame += AUDIO_BLOCK_FRAMES
        return block

    def _run(self) -> None:
        try:
            block = self._read()
            while not self._stop.is_set():
                try:
                    self._queue.put(block, timeout=_FEED_TIMEOUT_S)
                except queue.Full:
                    continue
                block = self._read()
        except Exception:
            _log.exception("no s'ha pogut llegir la música de la previsualització")


class StreamClock:
    """Implements Clock: the show time of the sample that is being heard."""

    def __init__(self, stream_time: Callable[[], float], from_s: float) -> None:
        self._stream_time = stream_time
        self._from = from_s
        self._lock = threading.Lock()
        self._anchor: tuple[float, float] | None = None
        """(show time of the first sample of the last block, when it is heard on the stream clock)."""
        self._heard_until = from_s
        """Show time up to which samples have been handed to the card (the clock stops there)."""
        self._last = from_s

    def block_played(self, show_s: float, dac_time: float, frames: int) -> None:
        """Called by the audio callback for every block of real sound."""
        with self._lock:
            self._anchor = (show_s, dac_time)
            self._heard_until = show_s + frames / SAMPLE_RATE

    def now(self) -> float:
        with self._lock:
            anchor = self._anchor
            if anchor is None:
                return self._last
            show_s, dac_time = anchor
            heard = show_s + (self._stream_time() - dac_time)
            self._last = max(self._last, min(heard, self._heard_until))
            return self._last


class _Session:
    """What one start() plays: the feeder, its clock and the frames already handed to the card."""

    def __init__(self, feeder: _Feeder, clock: StreamClock, from_s: float) -> None:
        self.feeder = feeder
        self.clock = clock
        self.from_s = from_s
        self.consumed = 0


class SoundDeviceOutput:
    """Implements AudioOutput with the default sound device (or the given stream factory).

    The stream stays open between stop() and the next start(), playing silence: closing and
    reopening it on every pause or jump makes Bluetooth headphones fade the sound in again for
    one or two seconds. It is closed after `keep_open_s` without sound (an open stream keeps
    Windows from sleeping) and by close().
    """

    def __init__(
        self, stream_factory: StreamFactory = sounddevice_stream, keep_open_s: float = KEEP_OPEN_S
    ) -> None:
        self._factory = stream_factory
        self._keep_open_s = keep_open_s
        self._lock = threading.Lock()
        self._stream: AudioStream | None = None
        self._session: _Session | None = None
        self._closer: threading.Timer | None = None
        self.underruns = 0
        """Blocks the card asked for before the feeder had them ready (they are played as silence)."""

    def start(self, source: AudioSource, from_s: float) -> StreamClock:
        self.stop()
        feeder = _Feeder(source, from_s)
        feeder.prime()
        with self._lock:
            self._cancel_closer()
            stream = self._stream
            opened = stream is None
            if stream is None:
                stream = self._factory(self._callback)
                self._stream = stream
            session = _Session(feeder, StreamClock(lambda: stream.time, from_s), from_s)
            self._session = session
        feeder.start()
        if opened:
            try:
                stream.start()
            except Exception:
                with self._lock:
                    self._session = None
                    self._stream = None
                feeder.stop()
                stream.close()
                raise
        return session.clock

    def stop(self) -> None:
        """Stops the sound now; the stream goes on with silence until it is closed."""
        with self._lock:
            session, self._session = self._session, None
            if self._stream is not None and self._closer is None:
                self._closer = threading.Timer(self._keep_open_s, self._close_if_silent)
                self._closer.daemon = True
                self._closer.start()
        if session is not None:
            session.feeder.stop()

    def close(self) -> None:
        """Stops the sound and closes the stream (when the player is closed)."""
        self.stop()
        with self._lock:
            self._cancel_closer()
            stream, self._stream = self._stream, None
        _close_stream(stream)

    @property
    def stream_open(self) -> bool:
        return self._stream is not None

    def _close_if_silent(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            self._closer = None
            stream, self._stream = self._stream, None
        _close_stream(stream)

    def _cancel_closer(self) -> None:
        if self._closer is not None:
            self._closer.cancel()
            self._closer = None

    def _callback(self, outdata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        session = self._session
        if session is None:
            outdata.fill(0)
            return
        block = session.feeder.take() if frames == AUDIO_BLOCK_FRAMES else None
        if block is None:
            outdata.fill(0)
            self.underruns += 1
            return
        outdata[:] = block
        show_s = session.from_s + session.consumed / SAMPLE_RATE
        session.clock.block_played(show_s, float(time_info.outputBufferDacTime), frames)
        session.consumed += frames


def _close_stream(stream: AudioStream | None) -> None:
    if stream is None:
        return
    try:
        stream.stop()
    except Exception:
        _log.warning("No s'ha pogut aturar el flux de so", exc_info=True)
    finally:
        stream.close()
