"""C09: SoundcardBackend against a stand-in for the soundcard module (no sound card, no Windows).

The real soundcard is tried only on the user's PC (tests/integration/recorder/test_so.py). Here a
fake module with soundcard 0.4.6's names checks what the backend does with it: the list, the exact
id (never soundcard's fuzzy name match), the errors and the discontinuities.
"""

from __future__ import annotations

import dataclasses
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

from passimaker.recorder import (
    RecorderDeviceError,
    RecorderDeviceLostError,
    RecorderMicrophoneDeniedError,
    RecorderNoDeviceError,
    SoundcardBackend,
    SourceKind,
    list_sources,
)
from passimaker.recorder.backend import CAPTURE_SAMPLE_RATE, translate_error
from tests.fakes.recorder import MICROPHONE, SPEAKERS


@dataclass
class _Recorder:
    channels: int
    packets: list[int] = field(default_factory=list[int])
    """Flags of the packets each record() reads (AUDCLNT_BUFFERFLAGS_*)."""
    error: Exception | None = None
    entered: int = 0
    exited: int = 0
    asked: list[int] = field(default_factory=list[int])

    def __enter__(self) -> _Recorder:
        self.entered += 1
        return self

    def __exit__(self, *args: object) -> None:
        self.exited += 1

    def _capture_buffer(self) -> tuple[object, int, int]:
        return object(), 0, self.packets.pop(0) if self.packets else 0

    def record(self, numframes: int) -> np.ndarray:
        self.asked.append(numframes)
        if self.error is not None:
            raise self.error
        for _ in range(2):
            self._capture_buffer()
        return np.zeros((numframes, self.channels), dtype=np.float32)


@dataclass
class _Mic:
    id: str
    name: str
    isloopback: bool
    device_channels: int | None = 2
    open_error: Exception | None = None
    opened: list[_Recorder] = field(default_factory=list[_Recorder])

    @property
    def channels(self) -> int:
        assert self.device_channels is not None, "soundcard asserts on formats it cannot read"
        return self.device_channels

    def recorder(self, samplerate: int, channels: int) -> _Recorder:
        assert samplerate == CAPTURE_SAMPLE_RATE
        if self.open_error is not None:
            raise self.open_error
        rec = _Recorder(channels)
        self.opened.append(rec)
        return rec


class _Soundcard(types.ModuleType):
    def __init__(self, mics: list[_Mic], default_out: str | None, default_in: str | None) -> None:
        super().__init__("soundcard")
        self.mics = mics
        self.default_out = default_out
        self.default_in = default_in

    def _device(self, device_id: str | None) -> Any:
        if device_id is None:
            raise RuntimeError("Error 0x80070490")
        return types.SimpleNamespace(id=device_id)

    def default_speaker(self) -> Any:
        return self._device(self.default_out)

    def default_microphone(self) -> Any:
        return self._device(self.default_in)

    def all_microphones(self, include_loopback: bool = False) -> list[_Mic]:
        return [m for m in self.mics if include_loopback or not m.isloopback]


@pytest.fixture
def soundcard(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Soundcard]:
    module = _Soundcard(
        [
            _Mic("{bt}", "Auriculars", True),
            _Mic(SPEAKERS.id, SPEAKERS.name, True, device_channels=None),
            _Mic(MICROPHONE.id, MICROPHONE.name, False, device_channels=1),
            # An input whose name contains the id of the speakers: soundcard's fuzzy match would find it.
            _Mic("{other}", f"Micro {SPEAKERS.id}", False),
        ],
        default_out=SPEAKERS.id,
        default_in=MICROPHONE.id,
    )
    monkeypatch.setitem(sys.modules, "soundcard", module)
    yield module


def test_lists_outputs_and_inputs(soundcard: _Soundcard) -> None:
    sources = list_sources(backend=SoundcardBackend())
    assert [(s.id, s.kind, s.is_default) for s in sources] == [
        (SPEAKERS.id, SourceKind.OUTPUT_LOOPBACK, True),
        ("{bt}", SourceKind.OUTPUT_LOOPBACK, False),
        (MICROPHONE.id, SourceKind.INPUT, True),
        ("{other}", SourceKind.INPUT, False),
    ]
    assert sources[0].channels == 2  # the format soundcard cannot read: stereo
    assert sources[2].channels == 1 and sources[0].sample_rate == CAPTURE_SAMPLE_RATE


def test_no_default_output(soundcard: _Soundcard) -> None:
    soundcard.default_out = None
    assert not any(
        s.is_default for s in SoundcardBackend().list_sources() if s.kind is SourceKind.OUTPUT_LOOPBACK
    )
    assert SoundcardBackend().default_output_id() is None


def test_records_blocks_of_the_asked_size(soundcard: _Soundcard) -> None:
    stream = SoundcardBackend(block_s=0.05).open(SPEAKERS)
    block = stream.read(0.2)
    assert block is not None and block.shape == (2400, 2) and block.dtype == np.float32
    assert (stream.sample_rate, stream.channels) == (CAPTURE_SAMPLE_RATE, 2)
    stream.close()
    stream.close()
    (rec,) = soundcard.mics[1].opened
    assert (rec.entered, rec.exited, rec.channels) == (1, 1, 2)


def test_counts_the_discontinuities_but_not_the_first_packet(soundcard: _Soundcard) -> None:
    stream = SoundcardBackend().open(SPEAKERS)
    (rec,) = soundcard.mics[1].opened
    rec.packets = [1, 0, 1, 1]  # WASAPI always flags the first packet
    stream.read(0.2)
    stream.read(0.2)
    assert stream.discontinuities() == 2
    stream.close()


def test_opens_the_exact_device_or_none(soundcard: _Soundcard) -> None:
    soundcard.mics.pop(1)  # the speakers are gone; only "Micro {speakers}" still mentions them
    with pytest.raises(RecorderNoDeviceError):
        SoundcardBackend().open(SPEAKERS)
    assert soundcard.mics[2].opened == []


def test_an_output_is_never_opened_as_an_input(soundcard: _Soundcard) -> None:
    with pytest.raises(RecorderNoDeviceError):
        SoundcardBackend().open(dataclasses.replace(MICROPHONE, id="{bt}"))


@pytest.mark.parametrize(
    ("message", "source", "expected"),
    [
        ("Error 0x80070005", MICROPHONE, RecorderMicrophoneDeniedError),
        ("Error 0x80070005", SPEAKERS, RecorderDeviceError),
        ("Error 0x88890004", SPEAKERS, RecorderDeviceLostError),
        ("Error 0x8889000a", SPEAKERS, RecorderDeviceError),
    ],
)
def test_errors_when_opening(
    soundcard: _Soundcard, message: str, source: Any, expected: type[Exception]
) -> None:
    for mic in soundcard.mics:
        mic.open_error = RuntimeError(message)
    with pytest.raises(expected) as caught:
        SoundcardBackend().open(source)
    assert message in str(caught.value)


def test_errors_while_reading(soundcard: _Soundcard) -> None:
    stream = SoundcardBackend().open(SPEAKERS)
    soundcard.mics[1].opened[0].error = RuntimeError("Error 0x88890004")
    with pytest.raises(RecorderDeviceLostError):
        stream.read(0.2)
    soundcard.mics[1].opened[0].error = RuntimeError("Error 0x80004005")
    with pytest.raises(RecorderDeviceError):
        stream.read(0.2)
    stream.close()


def test_without_soundcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "soundcard", None)
    with pytest.raises(RecorderDeviceError):
        SoundcardBackend().list_sources()
    with pytest.raises(RecorderDeviceError):
        SoundcardBackend().open(SPEAKERS)


def test_translate_error_keeps_recorder_errors() -> None:
    error = RecorderNoDeviceError("x")
    assert translate_error(error, SPEAKERS) is error


def test_importing_the_recorder_loads_neither_soundcard_nor_qt_nor_the_network() -> None:
    """soundcard only when a source is listed or opened; never Qt or yt-dlp (decision 0013)."""
    import subprocess

    code = (
        "import sys, passimaker.recorder\n"
        "bad = ('soundcard', 'PySide6', 'shiboken6', 'yt_dlp', 'urllib.request', 'http.client')\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in bad or m in bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
