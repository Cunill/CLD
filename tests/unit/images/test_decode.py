"""B4: decoding of every format, orientation, colour conversion and size rules."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from passimaker.images import CachedImageSource, ImageDecodeError
from passimaker.images.decode import parse_exif_datetime
from passimaker.model.types import Rotation
from tests.fixtures.generate import (  # pyright: ignore[reportPrivateUsage]
    PHOTO_SPECS,
    _synthetic_image,
    f_pattern,
    synthetic_rgb,
)
from tests.unit.images.helpers import dihedral, mean_abs_diff, photo_for
from tests.unit.images.samples import (
    P3_SAMPLE,
    TIFF_UPRIGHT_SIZE,
    expected_adobe_in_srgb,
    expected_p3_in_srgb,
    pattern,
    seed,
)

FULL = 100_000
SPECS = {spec.name: spec for spec in PHOTO_SPECS}


@pytest.fixture
def source() -> CachedImageSource:
    return CachedImageSource()


def _get(
    source: CachedImageSource, path: Path, size: int = FULL, rotation: Rotation = Rotation.R0
) -> np.ndarray:
    image = source.get_image(photo_for(path, rotation), size)
    assert image.dtype == np.uint8 and image.ndim == 3 and image.shape[2] == 3
    return image


# --- formats -------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["ratio_4x3.jpg", "ratio_9x16.jpg", "pano_3x1.jpg", "tiny_320x240.jpg"])
def test_jpeg_matches_the_generated_pixels(
    source: CachedImageSource, fixture_files: dict[str, Path], name: str
) -> None:
    spec = SPECS[name]
    image = _get(source, fixture_files[name])
    expected = np.asarray(_synthetic_image(spec.width, spec.height, seed(name)))
    assert mean_abs_diff(image, expected) < 4


def test_heic(source: CachedImageSource, fixture_files: dict[str, Path]) -> None:
    image = _get(source, fixture_files["photo.heic"])
    assert mean_abs_diff(image, synthetic_rgb(1200, 900, seed("photo.heic"))) < 6


def test_cmyk_jpeg_becomes_rgb(source: CachedImageSource, fixture_files: dict[str, Path]) -> None:
    image = _get(source, fixture_files["cmyk.jpg"])
    assert mean_abs_diff(image, synthetic_rgb(1200, 900, seed("cmyk.jpg"))) < 6


def test_16_bit_grayscale_png_keeps_its_levels(
    source: CachedImageSource, fixture_files: dict[str, Path]
) -> None:
    image = _get(source, fixture_files["gray16.png"])
    gray = np.asarray(Image.fromarray(synthetic_rgb(1000, 750, seed("gray16.png"))).convert("L"))
    for channel in range(3):
        np.testing.assert_array_equal(image[..., channel], gray)


@pytest.mark.parametrize("name", ["rgb16.png", "rgb16.tif"])
def test_16_bit_rgb_becomes_8_bit(source: CachedImageSource, samples: dict[str, Path], name: str) -> None:
    np.testing.assert_array_equal(_get(source, samples[name]), pattern("rgb16", 400, 300))


def test_png_transparency_is_composed_over_black(
    source: CachedImageSource, fixture_files: dict[str, Path]
) -> None:
    image = _get(source, fixture_files["alpha.png"])
    expected = synthetic_rgb(1000, 750, seed("alpha.png"))
    np.testing.assert_array_equal(image[187, 250], [0, 0, 0])  # centre of the transparent ellipse
    np.testing.assert_array_equal(image[600:, 600:], expected[600:, 600:])


def test_webp_partial_transparency_is_premultiplied(
    source: CachedImageSource, samples: dict[str, Path]
) -> None:
    image = _get(source, samples["alpha.webp"]).astype(np.int32)
    expected = pattern("webp_alpha", 300, 200).astype(np.int32)
    assert image[:, :150].max() == 0
    assert np.abs(image[:, 160:215] - expected[:, 160:215] * 128 / 255).max() <= 1.5
    np.testing.assert_array_equal(image[:, 230:], expected[:, 230:])


@pytest.mark.parametrize(("name", "pattern_name"), [("photo.bmp", "bmp"), ("photo.webp", "webp")])
def test_lossless_formats_are_exact(
    source: CachedImageSource, samples: dict[str, Path], name: str, pattern_name: str
) -> None:
    np.testing.assert_array_equal(_get(source, samples[name]), pattern(pattern_name, 640, 480))


def test_gif_gives_its_first_frame(source: CachedImageSource, samples: dict[str, Path]) -> None:
    first = np.asarray(Image.fromarray(pattern("gif", 320, 240)).quantize(64).convert("RGB"))
    np.testing.assert_array_equal(_get(source, samples["animated.gif"]), first)


def test_gif_transparency_is_black(source: CachedImageSource, samples: dict[str, Path]) -> None:
    image = _get(source, samples["transparent.gif"])
    assert image[:, :100].max() == 0
    assert (image[:, 100:] == [200, 120, 60]).all()


def test_grayscale_jpeg_has_three_equal_channels(source: CachedImageSource, samples: dict[str, Path]) -> None:
    image = _get(source, samples["gray.jpg"])
    assert (image[..., 0] == image[..., 1]).all() and (image[..., 1] == image[..., 2]).all()


def test_png_with_a_jpg_extension_is_read(source: CachedImageSource, samples: dict[str, Path]) -> None:
    np.testing.assert_array_equal(_get(source, samples["png_named.jpg"]), pattern("disguised", 320, 240))


# --- errors --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("corrupt.jpg", "images.corrupt"),
        ("not_an_image.jpg", "images.corrupt"),
        ("empty.jpg", "images.corrupt"),
        ("camera.cr2", "images.corrupt"),
        ("icon_named.png", "images.unsupported"),
    ],
)
def test_broken_files_raise_image_decode_error(
    source: CachedImageSource, fixture_files: dict[str, Path], samples: dict[str, Path], name: str, key: str
) -> None:
    path = fixture_files.get(name) or samples[name]
    with pytest.raises(ImageDecodeError) as info:
        source.get_image(photo_for(path), 500)
    assert info.value.message_key == key


def test_missing_file(source: CachedImageSource, tmp_path: Path) -> None:
    with pytest.raises(ImageDecodeError) as info:
        source.get_image(photo_for(tmp_path / "gone.jpg"), 500)
    assert info.value.message_key == "images.not_found"


@pytest.mark.parametrize("cut", [0.05, 0.3, 0.6, 0.95])
@pytest.mark.parametrize("name", ["ratio_4x3.jpg", "alpha.png", "photo.heic", "gray16.png"])
def test_truncated_files_never_raise_anything_else(
    source: CachedImageSource, fixture_files: dict[str, Path], tmp_path: Path, name: str, cut: float
) -> None:
    data = fixture_files[name].read_bytes()
    path = tmp_path / f"cut_{cut}_{name}"
    path.write_bytes(data[: int(len(data) * cut)])
    try:
        image = source.get_image(photo_for(path), 300)
    except ImageDecodeError as exc:
        assert exc.message_key in {"images.corrupt", "images.unsupported"}
    else:
        assert image.ndim == 3


# --- orientation and rotation --------------------------------------------------------------------


@pytest.mark.parametrize("orientation", range(1, 9))
def test_the_f_is_always_upright(
    source: CachedImageSource, fixture_files: dict[str, Path], orientation: int
) -> None:
    spec = SPECS[f"orient_{orientation}.jpg"]
    upright = f_pattern(*spec.oriented_size)
    image = _get(source, fixture_files[spec.name])
    assert image.shape[1::-1] == spec.oriented_size
    variants = [v for v in dihedral(upright) if v.shape == image.shape]
    diffs = [mean_abs_diff(image, v) for v in variants]
    assert int(np.argmin(diffs)) == 0 and diffs[0] < 4


def test_tiff_orientation(source: CachedImageSource, samples: dict[str, Path]) -> None:
    image = _get(source, samples["orient_6.tif"])
    np.testing.assert_array_equal(image, f_pattern(*TIFF_UPRIGHT_SIZE))


@pytest.mark.parametrize("rotation", list(Rotation))
@pytest.mark.parametrize("orientation", [1, 6, 7])
def test_manual_rotation_is_clockwise_after_exif(
    source: CachedImageSource, fixture_files: dict[str, Path], orientation: int, rotation: Rotation
) -> None:
    spec = SPECS[f"orient_{orientation}.jpg"]
    upright = f_pattern(*spec.oriented_size)
    expected = np.ascontiguousarray(np.rot90(upright, -rotation.value // 90))
    image = _get(source, fixture_files[spec.name], rotation=rotation)
    assert image.shape == expected.shape
    assert mean_abs_diff(image, expected) < 4


# --- colour --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["p3.jpg", "p3.png", "p3_nclx.heic"])
def test_display_p3_is_converted_to_srgb(
    source: CachedImageSource, samples: dict[str, Path], name: str
) -> None:
    image = _get(source, samples[name])
    centre = image[150, 200].astype(np.float64)
    expected = expected_p3_in_srgb(P3_SAMPLE)
    assert np.abs(centre - expected).max() <= 2, (centre, expected)
    assert np.abs(centre - np.array(P3_SAMPLE)).max() > 10  # the conversion did something


def test_adobe_rgb_is_converted_to_srgb(source: CachedImageSource, samples: dict[str, Path]) -> None:
    centre = _get(source, samples["adobe.jpg"])[150, 200].astype(np.float64)
    assert np.abs(centre - expected_adobe_in_srgb(P3_SAMPLE)).max() <= 2


@pytest.mark.parametrize("name", ["srgb_profile.jpg", "broken_profile.jpg"])
def test_srgb_and_unreadable_profiles_keep_the_values(
    source: CachedImageSource, samples: dict[str, Path], name: str
) -> None:
    centre = _get(source, samples[name])[150, 200].astype(np.int32)
    assert np.abs(centre - np.array(P3_SAMPLE)).max() <= 1


# --- size ----------------------------------------------------------------------------------------


def _check_size(image: np.ndarray, original: tuple[int, int], target: int) -> None:
    long_side = max(image.shape[:2])
    original_long = max(original)
    if original_long <= target:
        assert image.shape[1::-1] == original
    else:
        assert target <= long_side <= 2 * target
        short_side = min(image.shape[:2])
        assert abs(short_side - long_side * min(original) / original_long) <= 1  # rounding only


@pytest.mark.parametrize("target", [1, 50, 400, 1000, 2000, 2999, 3000, 4500, 7999, 8000, 12000])
def test_huge_jpeg_size_rules(fixture_files: dict[str, Path], target: int) -> None:
    image = CachedImageSource().get_image(photo_for(fixture_files["huge_8000x6000.jpg"]), target)
    _check_size(image, (8000, 6000), target)


def test_huge_jpeg_at_2000_px_uses_reduced_decoding(fixture_files: dict[str, Path]) -> None:
    image = CachedImageSource().get_image(photo_for(fixture_files["huge_8000x6000.jpg"]), 2000)
    assert image.shape == (1500, 2000, 3)  # 1/4 of the original, straight from the JPEG decoder
    full = _synthetic_image(8000, 6000, seed("huge_8000x6000.jpg"))
    expected = np.asarray(full.reduce(4))
    assert mean_abs_diff(image, expected) < 6


@settings(max_examples=40, deadline=None)
@given(
    name=st.sampled_from(["ratio_4x3.jpg", "pano_3x1.jpg", "alpha.png", "photo.heic", "orient_6.jpg"]),
    target=st.integers(1, 5000),
)
def test_size_rules_for_any_request(fixture_files: dict[str, Path], name: str, target: int) -> None:
    image = CachedImageSource().get_image(photo_for(fixture_files[name]), target)
    _check_size(image, SPECS[name].oriented_size, target)


def test_reduced_decoding_is_fast_enough_for_the_default_suite(fixture_files: dict[str, Path]) -> None:
    """Loose limit (10× the perf target) so that a regression to full decoding is caught on CI."""
    path = fixture_files["huge_8000x6000.jpg"]
    CachedImageSource().get_image(photo_for(path), 2000)  # warm the file cache
    start = time.perf_counter()
    CachedImageSource().get_image(photo_for(path), 2000)
    assert time.perf_counter() - start < 4.0


# --- EXIF dates ----------------------------------------------------------------------------------


def test_exif_dates() -> None:
    from datetime import datetime

    assert parse_exif_datetime("2024:05:01 10:00:00") == datetime(2024, 5, 1, 10, 0, 0)
    assert parse_exif_datetime("2024:05:01 10:00:00", "045") == datetime(2024, 5, 1, 10, 0, 0, 45000)
    assert parse_exif_datetime(b"2024-05-01T10:00:00\x00") == datetime(2024, 5, 1, 10, 0, 0)
    assert parse_exif_datetime("0000:00:00 00:00:00") is None
    assert parse_exif_datetime("    :  :     :  :  ") is None
    assert parse_exif_datetime(None) is None
    assert parse_exif_datetime(12345) is None
