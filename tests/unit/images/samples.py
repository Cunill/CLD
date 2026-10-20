"""Extra test photos for B4 (formats and colour cases that tests/fixtures/generate.py lacks).

Built from the shared generator's patterns so that colours stay deterministic. Kept here and
not in tests/fixtures so that blocks working in parallel do not touch the same file.
"""

from __future__ import annotations

import io
import zlib
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import ExifTags, Image

from passimaker.images.color import DISPLAY_P3_PRIMARIES, rgb_profile_bytes
from tests.fixtures.generate import f_pattern, synthetic_rgb

ADOBE_RGB_PRIMARIES = ((0.64, 0.33), (0.21, 0.71), (0.15, 0.06))
ADOBE_RGB_GAMMA = 563 / 256
TIFF_UPRIGHT_SIZE = (320, 480)
"""orient_6.tif shows an upright "F" of this (width, height) once its orientation is applied."""
P3_SAMPLE = (200, 100, 50)
"""A Display P3 colour inside the sRGB gamut."""

# Linear RGB -> linear sRGB (all D65), published values independent of passimaker.images.color.
P3_TO_SRGB = np.array([[1.2249, -0.2247, 0.0], [-0.0420, 1.0419, 0.0], [-0.0197, -0.0786, 1.0979]])
ADOBE_TO_SRGB = np.array([[1.3982832, -0.3982831, 0.0], [0.0, 1.0, 0.0], [0.0, -0.0429383, 1.0429383]])


def srgb_to_linear(values: NDArray[np.float64]) -> NDArray[np.float64]:
    v = values / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(values: NDArray[np.float64]) -> NDArray[np.float64]:
    v = np.clip(values, 0.0, 1.0)
    return 255.0 * np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def expected_p3_in_srgb(rgb: tuple[int, int, int]) -> NDArray[np.float64]:
    return linear_to_srgb(P3_TO_SRGB @ srgb_to_linear(np.array(rgb, dtype=np.float64)))


def expected_adobe_in_srgb(rgb: tuple[int, int, int]) -> NDArray[np.float64]:
    linear = (np.array(rgb, dtype=np.float64) / 255.0) ** ADOBE_RGB_GAMMA
    return linear_to_srgb(ADOBE_TO_SRGB @ linear)


def seed(name: str) -> int:
    return zlib.crc32(name.encode("utf-8"))


def pattern(name: str, width: int, height: int) -> NDArray[np.uint8]:
    """The pixels that a sample called `name` contains (as stored, before orientation)."""
    return synthetic_rgb(width, height, seed(name))


def exif_bytes(orientation: int = 1, capture: str | None = None) -> bytes:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    if capture is not None:
        exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = capture
    return exif.tobytes()


def write_jpeg(path: Path, pixels: NDArray[np.uint8], **params: object) -> Path:
    Image.fromarray(pixels).save(path, "JPEG", quality=95, **params)
    return path


def make_samples(folder: Path) -> dict[str, Path]:
    """Writes every extra sample into `folder` and returns {name: path}."""
    folder.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    def add(name: str) -> Path:
        out[name] = folder / name
        return out[name]

    Image.fromarray(pattern("bmp", 640, 480)).save(add("photo.bmp"), "BMP")
    stored = Image.fromarray(f_pattern(*TIFF_UPRIGHT_SIZE)).transpose(Image.Transpose.ROTATE_90)
    stored.save(add("orient_6.tif"), "TIFF", tiffinfo={ExifTags.Base.Orientation: 6})
    Image.fromarray(pattern("webp", 640, 480)).save(add("photo.webp"), "WEBP", lossless=True)

    first = Image.fromarray(pattern("gif", 320, 240)).quantize(64)
    second = Image.new("RGB", (320, 240), (0, 200, 0)).quantize(4)
    first.save(add("animated.gif"), "GIF", save_all=True, append_images=[second])
    palette = Image.new("P", (200, 200), 1)
    palette.putpalette([0, 0, 0, 200, 120, 60] + [0] * (256 * 3 - 6))
    palette.paste(0, (0, 0, 100, 200))
    palette.save(add("transparent.gif"), "GIF", transparency=0)

    p3_icc = rgb_profile_bytes("Display P3", DISPLAY_P3_PRIMARIES)
    flat = Image.new("RGB", (400, 300), P3_SAMPLE)
    flat.save(add("p3.jpg"), "JPEG", quality=100, subsampling=0, icc_profile=p3_icc)
    flat.save(add("p3.png"), "PNG", icc_profile=p3_icc)
    adobe_icc = rgb_profile_bytes("Adobe RGB (1998)", ADOBE_RGB_PRIMARIES, ADOBE_RGB_GAMMA)
    flat.save(add("adobe.jpg"), "JPEG", quality=100, subsampling=0, icc_profile=adobe_icc)
    flat.save(add("srgb_profile.jpg"), "JPEG", quality=100, subsampling=0, icc_profile=_srgb_icc())
    flat.save(
        add("broken_profile.jpg"), "JPEG", quality=100, subsampling=0, icc_profile=b"not a profile" * 20
    )
    flat.save(add("p3_nclx.heic"), "HEIF", quality=100, color_primaries=12, transfer_characteristics=13)

    rgb16 = (pattern("rgb16", 400, 300).astype(np.uint16) * 257)[..., ::-1]  # OpenCV is BGR
    for ext in (".png", ".tif"):
        ok, buffer = cv2.imencode(ext, np.ascontiguousarray(rgb16))
        assert ok
        add(f"rgb16{ext}").write_bytes(buffer.tobytes())
    gray = cv2.cvtColor(pattern("gray", 400, 300), cv2.COLOR_RGB2GRAY)
    Image.fromarray(gray).save(add("gray.jpg"), "JPEG", quality=95)
    rgba = Image.fromarray(pattern("webp_alpha", 300, 200)).convert("RGBA")
    alpha = np.full((200, 300), 255, dtype=np.uint8)
    alpha[:, :150] = 0
    alpha[:, 150:225] = 128
    rgba.putalpha(Image.fromarray(alpha))
    rgba.save(add("alpha.webp"), "WEBP", lossless=True)

    Image.fromarray(pattern("small", 63, 200)).save(add("too_small.png"), "PNG")
    Image.fromarray(pattern("limit", 64, 200)).save(add("just_big_enough.png"), "PNG")
    write_jpeg(add("dated.jpg"), pattern("dated", 320, 240), exif=exif_bytes(1, "2023:07:14 18:30:05"))
    add("camera.cr2").write_bytes(b"II*\x00" + bytes(200))
    add("camera.dng").write_bytes(b"II*\x00" + bytes(200))
    add("song.mp3").write_bytes(b"ID3" + bytes(100))
    add("png_named.jpg").write_bytes(_png_bytes(pattern("disguised", 320, 240)))
    add("empty.jpg").write_bytes(b"")
    Image.fromarray(pattern("icon", 100, 100)).save(add("icon_named.png"), "ICO")
    return out


def _png_bytes(pixels: NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, "PNG")
    return buffer.getvalue()


def _srgb_icc() -> bytes:
    from PIL import ImageCms

    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return profile.tobytes()
