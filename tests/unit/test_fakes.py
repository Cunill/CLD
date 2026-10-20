"""B0: the test doubles behave as documented, so later blocks can rely on them."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from passi.audio import AudioSource
from passi.images import ImageSource
from passi.model.types import MotionType, Photo
from tests.fakes.audio import ToneAudioSource
from tests.fakes.clock import SimulatedClock
from tests.fakes.images import SyntheticImageSource
from tests.fakes.motion import fixed_motion, fixed_window_at
from tests.fakes.timeline import fixed_query, fixed_timeline


def test_synthetic_images_keep_aspect_and_are_deterministic() -> None:
    source: ImageSource = SyntheticImageSource()
    photo = Photo("p1", Path("a.jpg"), None, 4000, 3000)
    a = source.get_image(photo, 800)
    b = source.get_image(photo, 800)
    assert a.shape == (600, 800, 3) and a.dtype == np.uint8
    assert np.array_equal(a, b)
    small = Photo("p2", Path("b.jpg"), None, 320, 240)
    assert source.get_image(small, 1920).shape == (240, 320, 3)


def test_tone_source_has_expected_frequency_and_silence_after_end() -> None:
    source: AudioSource = ToneAudioSource(duration_s=2.0, frequency=440.0)
    block = source.read(0.5, 48000)
    assert block.shape == (48000, 2) and block.dtype == np.float32
    spectrum = np.abs(np.fft.rfft(block[:, 0]))
    assert abs(np.argmax(spectrum) - 440) <= 1
    assert np.all(source.read(2.5, 1000) == 0)


def test_simulated_clock() -> None:
    clock = SimulatedClock()
    clock.advance(0.5)
    assert clock.now() == 0.5
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_fixed_timeline_opacities() -> None:
    tl = fixed_timeline(["a", "b", "c"], duration_s=5.0, crossfade_s=1.0, fade_s=1.0)
    assert tl.total_duration_s == 15.0 and tl.total_frames == 450
    mid = fixed_query(tl, 5.0)
    assert [layer.photo_id for layer in mid.layers] == ["a", "b"]
    assert sum(layer.opacity for layer in mid.layers) == pytest.approx(1.0)
    assert fixed_query(tl, 0.0).black_level == pytest.approx(1.0)
    assert fixed_query(tl, 7.0).black_level == 0.0


@pytest.mark.parametrize("motion_type", list(MotionType))
def test_fixed_motions_stay_inside_the_canvas(motion_type: MotionType) -> None:
    motion = fixed_motion(motion_type)
    for p in np.linspace(0, 1, 21):
        w = fixed_window_at(motion, float(p))
        half = 0.5 / w.scale
        assert w.scale >= 1.0
        assert half - 1e-9 <= w.centre_x <= 1 - half + 1e-9
        assert half - 1e-9 <= w.centre_y <= 1 - half + 1e-9
