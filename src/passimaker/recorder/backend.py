"""The capture backend: the only part that talks to the sound system (soundcard 0.4.6, block C08).

Recorder and Monitor open the source, read it and close it in their own capture thread, so the
backend only has to deliver blocks; the tests use a fake one (tests/fakes/recorder.py) with tones
and silences. SoundcardBackend imports soundcard only inside its methods, never at import time.

What block C08 learnt on Windows and SoundcardBackend applies:
- COM: soundcard does not initialise it in other threads, so every method (and every open stream,
  until close) holds CoInitializeEx(COINIT_MULTITHREADED) in the calling thread.
- A change of the default output while recording raises no error in WASAPI: the capture goes on
  from the old output, in silence. Recorder and Monitor call default_output_id() every
  defaults.RECORD_DEVICE_POLL_S and treat a change as a lost device.
- WASAPI's data discontinuities (now and then with Bluetooth, without losing samples) are logged
  and counted, and stop nothing.
- 48 kHz is asked of WASAPI, which converts from the device's own rate and mixes 5.1 to stereo.
- A microphone that Windows' privacy settings deny fails with 0x80070005.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import sys
from collections.abc import Generator
from typing import Any, Protocol

import numpy as np

from passimaker.model import defaults
from passimaker.recorder.types import (
    AudioFrames,
    AudioSource,
    RecorderDeviceError,
    RecorderDeviceLostError,
    RecorderError,
    RecorderMicrophoneDeniedError,
    RecorderNoDeviceError,
    SourceKind,
)

CAPTURE_SAMPLE_RATE = 48000
"""Asked of WASAPI for every source (soundcard turns on its automatic conversion)."""

_log = logging.getLogger(__name__)

# HRESULTs that soundcard reports as "Error 0x…" (um/audioclient.h, winerror.h).
_DEVICE_INVALIDATED = "0x88890004"
_ACCESS_DENIED = "0x80070005"
_COINIT_MULTITHREADED = 0x0
_S_OK = 0
_S_FALSE = 1
_DATA_DISCONTINUITY = 0x1
"""AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY."""


class CaptureStream(Protocol):
    """An open source. Used from a single thread (the capture thread that opened it)."""

    @property
    def sample_rate(self) -> int: ...

    @property
    def channels(self) -> int:
        """Channels of the blocks it returns: 1 or 2 (5.1 and others arrive mixed down to stereo)."""
        ...

    def read(self, timeout_s: float) -> AudioFrames | None:
        """The next block, shape (frames, channels); None if nothing arrived within `timeout_s`.

        Raises RecorderDeviceLostError if the device was disconnected or replaced and
        RecorderDeviceError for any other failure. Silence (nothing playing) is a block of zeros:
        with WASAPI loopback no packets arrive then, and soundcard fills the time with zeros.
        """
        ...

    def discontinuities(self) -> int:
        """Data discontinuities reported so far by the sound system (for the log; block C08)."""
        ...

    def close(self) -> None:
        """Stop capturing; never raises."""
        ...


class CaptureBackend(Protocol):
    def list_sources(self) -> tuple[AudioSource, ...]:
        """Every output (loopback) and input; list_sources() puts them in order."""
        ...

    def open(self, source: AudioSource) -> CaptureStream:
        """Start capturing, from the capture thread. RecorderNoDeviceError if `source` is gone,
        RecorderMicrophoneDeniedError if Windows denies an input, RecorderDeviceError otherwise."""
        ...

    def default_output_id(self) -> str | None:
        """The id of the current default output (None if there is none or it cannot be read)."""
        ...


# --- soundcard (Windows) ------------------------------------------------------------------------------


class SoundcardBackend:
    """CaptureBackend with soundcard (WASAPI on Windows; approved by the user, G10)."""

    def __init__(self, block_s: float = defaults.RECORD_BLOCK_S) -> None:
        self._block_frames = max(1, round(block_s * CAPTURE_SAMPLE_RATE))

    def list_sources(self) -> tuple[AudioSource, ...]:
        sc = _soundcard()
        try:
            with _com():
                default_out = _default_id(sc.default_speaker)
                default_in = _default_id(sc.default_microphone)
                found: list[AudioSource] = []
                for mic in sc.all_microphones(include_loopback=True):
                    loopback = bool(mic.isloopback)
                    found.append(
                        AudioSource(
                            id=str(mic.id),
                            name=str(mic.name),
                            kind=SourceKind.OUTPUT_LOOPBACK if loopback else SourceKind.INPUT,
                            is_default=mic.id == (default_out if loopback else default_in),
                            sample_rate=_mix_rate(mic),
                            channels=_device_channels(mic),
                        )
                    )
                return tuple(found)
        except RecorderError:
            raise
        except Exception as error:
            raise RecorderDeviceError(_describe(error)) from error

    def open(self, source: AudioSource) -> CaptureStream:
        sc = _soundcard()
        com = _ComScope()
        try:
            loopback = source.kind is SourceKind.OUTPUT_LOOPBACK
            # Never get_microphone(): with an id that is gone it falls back to a name match.
            mic = next(
                (
                    m
                    for m in sc.all_microphones(include_loopback=True)
                    if m.id == source.id and bool(m.isloopback) == loopback
                ),
                None,
            )
            if mic is None:
                raise RecorderNoDeviceError(source.name)
            recorder = mic.recorder(samplerate=CAPTURE_SAMPLE_RATE, channels=source.recorded_channels)
            recorder.__enter__()
        except RecorderError:
            com.release()
            raise
        except Exception as error:
            com.release()
            raise translate_error(error, source) from error
        return _SoundcardStream(recorder, source, self._block_frames, com)

    def default_output_id(self) -> str | None:
        sc = _soundcard()
        try:
            with _com():
                return _default_id(sc.default_speaker)
        except Exception as error:
            _log.warning("Could not read the default output: %s", _describe(error))
            return None


class _SoundcardStream:
    def __init__(self, recorder: Any, source: AudioSource, block_frames: int, com: _ComScope) -> None:
        self._recorder = recorder
        self._source = source
        self._block_frames = block_frames
        self._com = com
        self._discontinuities = 0
        self._first_packet = True
        self._closed = False
        self._count_discontinuities()

    @property
    def sample_rate(self) -> int:
        return CAPTURE_SAMPLE_RATE

    @property
    def channels(self) -> int:
        return self._source.recorded_channels

    def read(self, timeout_s: float) -> AudioFrames | None:
        # soundcard waits for the whole block (a few block lengths at most: with nothing playing it
        # returns zeros), so `timeout_s` is not needed here.
        del timeout_s
        try:
            data = self._recorder.record(numframes=self._block_frames)
        except Exception as error:
            raise translate_error(error, self._source) from error
        block = np.asarray(data, dtype=np.float32)
        return block.reshape(-1, 1) if block.ndim == 1 else block

    def discontinuities(self) -> int:
        return self._discontinuities

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._recorder.__exit__(None, None, None)
        except Exception as error:
            _log.warning("Closing the capture failed: %s", _describe(error))
        finally:
            self._com.release()

    def _count_discontinuities(self) -> None:
        """soundcard only warns about them: wrap its packet reader (pinned soundcard 0.4.6) to count
        and log them without touching the process-wide warning filters from this thread."""
        original = getattr(self._recorder, "_capture_buffer", None)
        if original is None:
            return

        def capture_buffer() -> Any:
            data, frames, flags = original()
            if self._first_packet:
                self._first_packet = False  # WASAPI always flags the first packet
            elif int(flags) & _DATA_DISCONTINUITY:
                self._discontinuities += 1
                _log.info("WASAPI data discontinuity (%d so far)", self._discontinuities)
            return data, frames, flags

        self._recorder._capture_buffer = capture_buffer


def translate_error(error: BaseException, source: AudioSource) -> RecorderError:
    """soundcard raises RuntimeError("Error 0x…"): the RecorderError the interface can show."""
    if isinstance(error, RecorderError):
        return error
    text = _describe(error)
    if _DEVICE_INVALIDATED in text.lower():
        return RecorderDeviceLostError(text)
    if _ACCESS_DENIED in text.lower() and source.kind is SourceKind.INPUT:
        return RecorderMicrophoneDeniedError(text)
    return RecorderDeviceError(text)


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _soundcard() -> Any:
    """Imported before our CoInitializeEx: on import soundcard initialises COM itself and fails if the
    thread already has it as multithreaded."""
    try:
        import soundcard  # pyright: ignore[reportMissingTypeStubs]  (a plain import: PyInstaller finds it)
    except Exception as error:
        raise RecorderDeviceError(_describe(error)) from error
    return soundcard


def _default_id(get: Any) -> str | None:
    try:
        return str(get().id)
    except Exception:  # no device of that kind
        return None


def _device_channels(mic: Any) -> int:
    """soundcard reads them with asserts on the device format: a device it cannot read is taken as
    stereo (WASAPI converts) instead of stopping the whole list."""
    try:
        return max(1, int(mic.channels))
    except Exception:
        return 2


def _mix_rate(mic: Any) -> int:
    """The rate Windows mixes at (soundcard does not tell it): IAudioClient::GetMixFormat."""
    try:
        mf: Any = importlib.import_module("soundcard.mediafoundation")
        client = mic._audio_client()
        fmt = mf._ffi.new("WAVEFORMATEXTENSIBLE**")
        mf._com.check_error(client[0][0].lpVtbl.GetMixFormat(client[0], fmt))
        rate = int(fmt[0][0].Format.nSamplesPerSec)
        mf._ole32.CoTaskMemFree(fmt[0])
        mf._com.release(client)
        return rate
    except Exception:
        return CAPTURE_SAMPLE_RATE


class _ComScope:
    """COM initialised (multithreaded) in the calling thread until release()."""

    def __init__(self) -> None:
        self._initialised = _co_initialize()

    def release(self) -> None:
        if self._initialised:
            self._initialised = False
            _co_uninitialize()


@contextlib.contextmanager
def _com() -> Generator[None]:
    scope = _ComScope()
    try:
        yield
    finally:
        scope.release()


def _co_initialize() -> bool:
    """True if the call must be balanced with CoUninitialize. A thread that already is
    single-threaded (Qt's main thread) answers RPC_E_CHANGED_MODE: COM works there, nothing to undo."""
    if sys.platform == "win32":
        import ctypes

        hr = ctypes.windll.ole32.CoInitializeEx(None, _COINIT_MULTITHREADED) & 0xFFFFFFFF
        return hr in (_S_OK, _S_FALSE)
    return False


def _co_uninitialize() -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.ole32.CoUninitialize()
