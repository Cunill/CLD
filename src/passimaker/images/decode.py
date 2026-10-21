"""Reading photo headers and decoding pixels at a reduced size (Pillow + pillow-heif).

Shared by the importer (headers only) and the image cache (pixels). Pixels are always returned
as sRGB "RGB" 8-bit with the EXIF orientation applied; transparency is composed over black.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pillow_heif
from PIL import ExifTags, Image, UnidentifiedImageError

from passimaker.common import RGBImage
from passimaker.images.color import embedded_icc, profile_description, to_srgb
from passimaker.model.types import Rotation

pillow_heif.register_heif_opener()  # pyright: ignore[reportUnknownMemberType]

Image.init()
ACCEPTED_FORMATS: tuple[str, ...] = tuple(
    f for f in ("JPEG", "PNG", "HEIF", "BMP", "DIB", "TIFF", "WEBP", "GIF") if f in Image.OPEN
)
"""Pillow format ids that are read; anything else is rejected even with a known extension.
JPEG files with several pictures (MPO) are opened by the JPEG plugin."""

MAX_IMAGE_PIXELS = 200_000_000
"""Pillow warns above this and refuses twice this (decompression bombs). Photos of 50–100 MP must open."""
Image.MAX_IMAGE_PIXELS = max(Image.MAX_IMAGE_PIXELS or 0, MAX_IMAGE_PIXELS)

EXIF_ORIENTATION_TAG = 0x0112
_DATE_TAGS: tuple[tuple[int, int], ...] = (
    (ExifTags.Base.DateTimeOriginal, ExifTags.Base.SubsecTimeOriginal),
    (ExifTags.Base.DateTimeDigitized, ExifTags.Base.SubsecTimeDigitized),
)
_DATE_RE = re.compile(r"(\d{4})[:\-/.](\d{2})[:\-/.](\d{2})[ T](\d{2}):(\d{2}):(\d{2})")

# What PIL.ImageOps.exif_transpose does for each orientation value.
_EXIF_TRANSPOSE: dict[int, Image.Transpose] = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
# Manual rotation is clockwise; Pillow's ROTATE_* are counter-clockwise.
_ROTATION_TRANSPOSE: dict[Rotation, Image.Transpose] = {
    Rotation.R90: Image.Transpose.ROTATE_270,
    Rotation.R180: Image.Transpose.ROTATE_180,
    Rotation.R270: Image.Transpose.ROTATE_90,
}
_16_BIT_MODES = frozenset({"I;16", "I;16L", "I;16B", "I;16N"})


class ImageReadError(Exception):
    """Internal: a file could not be read. `reason` is one of the REASON_* values."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


REASON_NOT_FOUND = "not_found"
REASON_CORRUPT = "corrupt"
REASON_UNSUPPORTED = "unsupported"
REASON_TOO_LARGE = "too_large"
REASON_OUT_OF_MEMORY = "out_of_memory"


@dataclass(frozen=True, slots=True)
class HeaderInfo:
    stored_width: int
    stored_height: int
    orientation: int
    capture_time: datetime | None
    color_profile: str | None
    format: str

    @property
    def oriented_size(self) -> tuple[int, int]:
        if self.orientation in (5, 6, 7, 8):
            return self.stored_height, self.stored_width
        return self.stored_width, self.stored_height


def _open(path: Path) -> Image.Image:
    try:
        return Image.open(path, formats=ACCEPTED_FORMATS)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ImageReadError(REASON_NOT_FOUND, str(exc)) from exc
    except Image.DecompressionBombError as exc:
        raise ImageReadError(REASON_TOO_LARGE, str(exc)) from exc
    except UnidentifiedImageError as exc:
        raise ImageReadError(_unidentified_reason(path), str(exc)) from exc
    except MemoryError as exc:
        raise ImageReadError(REASON_OUT_OF_MEMORY) from exc
    except Exception as exc:  # Pillow raises many types on malformed headers
        raise ImageReadError(REASON_CORRUPT, f"{type(exc).__name__}: {exc}") from exc


def _unidentified_reason(path: Path) -> str:
    """An image in a format that is not accepted (e.g. an icon) or not an image at all."""
    try:
        with Image.open(path):
            return REASON_UNSUPPORTED
    except Exception:
        return REASON_CORRUPT


def _exif(image: Image.Image) -> Image.Exif:
    """EXIF without decoding pixels (PngImageFile.getexif() would load the whole image)."""
    if image.format == "PNG":
        exif = Image.Exif()
        raw = image.info.get("exif")
        if isinstance(raw, bytes):
            exif.load(raw)
        return exif
    return image.getexif()


_SELF_ORIENTING_FORMATS = frozenset({"TIFF", "HEIF"})
"""Pillow's TIFF plugin and pillow-heif report the oriented size and orient the pixels on load."""


def _orientation(image: Image.Image) -> int:
    """The EXIF orientation that still has to be applied to the decoded pixels."""
    if image.format in _SELF_ORIENTING_FORMATS:
        return 1
    value = _exif(image).get(EXIF_ORIENTATION_TAG, 1)
    return value if isinstance(value, int) and 1 <= value <= 8 else 1


def parse_exif_datetime(text: object, subsec: object = None) -> datetime | None:
    """EXIF "YYYY:MM:DD HH:MM:SS" (plus optional sub-seconds) as a naive datetime; None if invalid."""
    if isinstance(text, bytes):
        text = text.decode("ascii", "replace")
    if not isinstance(text, str):
        return None
    match = _DATE_RE.search(text)
    if match is None:
        return None
    try:
        when = datetime(*(int(part) for part in match.groups()))  # pyright: ignore[reportArgumentType]
    except ValueError:
        return None
    if isinstance(subsec, bytes):
        subsec = subsec.decode("ascii", "replace")
    if isinstance(subsec, str):
        digits = "".join(ch for ch in subsec if ch.isdigit())[:6]
        if digits:
            when = when.replace(microsecond=int(digits.ljust(6, "0")))
    return when


def _capture_time(exif: Image.Exif) -> datetime | None:
    try:
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:  # broken EXIF sub-IFD: the photo is still usable
        return None
    for date_tag, subsec_tag in _DATE_TAGS:
        when = parse_exif_datetime(ifd.get(date_tag), ifd.get(subsec_tag))
        if when is not None:
            return when
    return None


def read_header(path: Path) -> HeaderInfo:
    """Size, orientation, capture date and colour profile, reading only the file header."""
    with _open(path) as image:
        try:
            width, height = image.size
            exif = _exif(image)
            icc = embedded_icc(image.info)
            info = HeaderInfo(
                stored_width=width,
                stored_height=height,
                orientation=_orientation(image),
                capture_time=_capture_time(exif),
                color_profile=profile_description(icc) if icc else None,
                format=image.format or "",
            )
        except MemoryError as exc:
            raise ImageReadError(REASON_OUT_OF_MEMORY) from exc
        except Exception as exc:
            raise ImageReadError(REASON_CORRUPT, f"{type(exc).__name__}: {exc}") from exc
    if width <= 0 or height <= 0:
        raise ImageReadError(REASON_CORRUPT, "empty image")
    return info


def _draft_size(width: int, height: int, min_long_side: int) -> tuple[int, int]:
    scale = min_long_side / max(width, height)
    return max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale))


def _normalise_mode(image: Image.Image) -> Image.Image:
    """To "RGB", "L" or "CMYK", or to premultiplied "RGBa" / "La" (= composed over black)."""
    mode = image.mode
    if mode in _16_BIT_MODES or mode == "I":
        values = np.asarray(image).astype(np.int64)
        if mode == "I" and values.max(initial=0) <= 255:
            return Image.fromarray(np.clip(values, 0, 255).astype(np.uint8))
        return Image.fromarray((np.clip(values, 0, 65535) >> 8).astype(np.uint8))
    if mode == "F":
        values = np.asarray(image, dtype=np.float32)
        top = 1.0 if values.max(initial=0.0) <= 1.0 else 255.0
        return Image.fromarray(np.clip(values * (255.0 / top), 0, 255).round().astype(np.uint8))
    if mode == "CMYK":
        return image
    gray = mode in ("1", "L", "LA", "La")
    if image.has_transparency_data:
        return image.convert("LA" if gray else "RGBA").convert("La" if gray else "RGBa")
    if mode in ("RGB", "L"):
        return image
    return image.convert("L" if gray else "RGB")


def _drop_alpha(image: Image.Image) -> Image.Image:
    """Premultiplied colour channels are the photo composed over black."""
    if image.mode == "RGBa":
        return Image.fromarray(np.ascontiguousarray(np.asarray(image)[..., :3]))
    if image.mode == "La":
        return Image.fromarray(np.ascontiguousarray(np.asarray(image)[..., 0]))
    return image


def decode(path: Path, min_long_side: int, rotation: Rotation = Rotation.R0) -> tuple[RGBImage, bool]:
    """Decodes `path` as sRGB RGB uint8 with EXIF orientation and `rotation` applied.

    The long side is >= min_long_side (or the original size if it is smaller) and below twice
    min_long_side: JPEG files are decoded directly at 1/2, 1/4 or 1/8 of their size.
    Returns the image and whether it has the original size.
    """
    target = max(1, int(min_long_side))
    with _open(path) as image:
        try:
            orientation = _orientation(image)
            icc = embedded_icc(image.info)
            original_long_side = max(image.size)
            if image.format in ("JPEG", "MPO") and max(image.size) >= 2 * target:
                image.draft(image.mode, _draft_size(*image.size, target))
            image.load()  # pyright: ignore[reportUnknownMemberType]
            pixels = _normalise_mode(image)
            factor = max(pixels.size) // target
            if factor >= 2:
                pixels = pixels.reduce(factor)
            complete = max(pixels.size) == original_long_side
            pixels = to_srgb(_drop_alpha(pixels), icc)
        except MemoryError as exc:
            raise ImageReadError(REASON_OUT_OF_MEMORY) from exc
        except ImageReadError:
            raise
        except Exception as exc:  # truncated or malformed pixel data
            raise ImageReadError(REASON_CORRUPT, f"{type(exc).__name__}: {exc}") from exc
    transpose = _EXIF_TRANSPOSE.get(orientation)
    if transpose is not None:
        pixels = pixels.transpose(transpose)
    manual = _ROTATION_TRANSPOSE.get(rotation)
    if manual is not None:
        pixels = pixels.transpose(manual)
    array: Any = np.asarray(pixels, dtype=np.uint8)
    return np.ascontiguousarray(array), complete
