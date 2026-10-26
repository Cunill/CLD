"""C09: list_sources, outputs first and the defaults first (decision 0013, G6)."""

from __future__ import annotations

import pytest

from passimaker.recorder import AudioSource, RecorderDeviceError, SourceKind, list_sources
from tests.fakes.recorder import HEADPHONES, MICROPHONE, SPEAKERS, SURROUND, FakeCaptureBackend

LINE_IN = AudioSource(
    id="{line}",
    name="Entrada de línia",
    kind=SourceKind.INPUT,
    is_default=False,
    sample_rate=48000,
    channels=2,
)


def test_outputs_first_and_the_default_first_of_all() -> None:
    backend = FakeCaptureBackend(sources=(LINE_IN, HEADPHONES, MICROPHONE, SURROUND, SPEAKERS))
    assert list_sources(backend=backend) == (SPEAKERS, HEADPHONES, SURROUND, MICROPHONE, LINE_IN)


def test_no_device_at_all() -> None:
    assert list_sources(backend=FakeCaptureBackend(sources=())) == ()


def test_the_sound_system_fails() -> None:
    with pytest.raises(RecorderDeviceError):
        list_sources(backend=FakeCaptureBackend(list_error=RecorderDeviceError("x")))
