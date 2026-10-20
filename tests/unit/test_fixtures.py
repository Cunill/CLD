"""B0: the generated test data is valid, oriented as declared and deterministic."""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import numpy as np
import pillow_heif
import pytest
from PIL import Image, ImageOps

from tests.fixtures.generate import (
    BROKEN_FILES,
    MAX_MAGENTA_EXCESS,
    PHOTO_SPECS,
    TONE_SPECS,
    f_pattern,
    generate_all,
)

pillow_heif.register_heif_opener()


@pytest.mark.parametrize("spec", PHOTO_SPECS, ids=[s.name for s in PHOTO_SPECS])
def test_photos_open_with_declared_size(fixture_files: dict[str, Path], spec: object) -> None:
    from tests.fixtures.generate import PhotoSpec

    assert isinstance(spec, PhotoSpec)
    with Image.open(fixture_files[spec.name]) as img:
        assert img.size == (spec.width, spec.height)
        oriented = ImageOps.exif_transpose(img)
        assert oriented.size == spec.oriented_size


@pytest.mark.parametrize("orientation", range(1, 9))
def test_orientation_fixtures_show_an_upright_f(fixture_files: dict[str, Path], orientation: int) -> None:
    with Image.open(fixture_files[f"orient_{orientation}.jpg"]) as img:
        upright = np.asarray(ImageOps.exif_transpose(img).convert("RGB"), dtype=np.float32)
    reference = f_pattern(upright.shape[1], upright.shape[0]).astype(np.float32)
    assert np.abs(upright - reference).mean() < 4.0


def test_synthetic_photos_contain_no_sentinel_magenta(fixture_files: dict[str, Path]) -> None:
    for name in ("ratio_4x3.jpg", "pano_3x1.jpg", "photo.heic"):
        with Image.open(fixture_files[name]) as img:
            rgb = np.asarray(img.convert("RGB")).astype(np.int16)
        excess = np.minimum(rgb[..., 0] - rgb[..., 1], rgb[..., 2] - rgb[..., 1])
        assert excess.max() < MAX_MAGENTA_EXCESS


def test_special_formats(fixture_files: dict[str, Path]) -> None:
    with Image.open(fixture_files["cmyk.jpg"]) as img:
        assert img.mode == "CMYK"
    with Image.open(fixture_files["alpha.png"]) as img:
        assert img.mode == "RGBA"
        assert img.getchannel("A").getextrema() == (0, 255)
    with Image.open(fixture_files["gray16.png"]) as img:
        assert img.mode.startswith("I;16")
    with Image.open(fixture_files["photo.heic"]) as img:
        assert img.format == "HEIF"
        assert img.getexif().get_ifd(0x8769).get(0x9003) == "2024:05:09 10:00:00"
    with Image.open(fixture_files["ratio_4x3.jpg"]) as img:
        assert img.getexif().get_ifd(0x8769).get(0x9003) == "2024:05:01 10:00:00"


@pytest.mark.parametrize("name", BROKEN_FILES)
def test_broken_files_do_not_decode(fixture_files: dict[str, Path], name: str) -> None:
    with pytest.raises(OSError), Image.open(fixture_files[name]) as img:
        img.load()


def test_tones_have_declared_duration_and_level(fixture_files: dict[str, Path]) -> None:
    for spec in TONE_SPECS:
        with wave.open(str(fixture_files[f"{spec.name}.wav"])) as w:
            assert w.getframerate() == 48000 and w.getnchannels() == 2
            assert w.getnframes() == round(spec.duration_s * 48000)
            samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        peak = np.abs(samples).max() / 32767
        assert abs(peak - 0.25) < 0.001
        for fmt in ("mp3", "m4a", "flac", "ogg"):
            assert fixture_files[f"{spec.name}.{fmt}"].stat().st_size > 1000


def _hashes(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


@pytest.mark.lent
def test_generation_is_deterministic(tmp_path: Path) -> None:
    generate_all(tmp_path / "a")
    generate_all(tmp_path / "b")
    assert _hashes(tmp_path / "a") == _hashes(tmp_path / "b")
