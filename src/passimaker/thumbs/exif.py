"""The thumbnail embedded in the EXIF data of JPEG files (IFD1), oriented like the photo."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import ExifTags, Image

from passimaker.common import RGBImage
from passimaker.images.color import embedded_icc, to_srgb
from passimaker.model.types import Rotation
from passimaker.thumbs.params import (
    EXIF_THUMBNAIL_ASPECT_TOLERANCE,
    EXIF_THUMBNAIL_MIN_SIZE,
    REDUCED_DECODE_FORMATS,
)

_log = logging.getLogger(__name__)

_ORIENTATION_TAG = 0x0112
_THUMBNAIL_OFFSET_TAG = 0x0201  # JPEGInterchangeFormat
_THUMBNAIL_LENGTH_TAG = 0x0202  # JPEGInterchangeFormatLength
_EXIF_HEADER = b"Exif\x00\x00"

# The same transposes as passimaker.images.decode (EXIF orientation, then clockwise manual rotation).
_EXIF_TRANSPOSE: dict[int, Image.Transpose] = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
_ROTATION_TRANSPOSE: dict[Rotation, Image.Transpose] = {
    Rotation.R90: Image.Transpose.ROTATE_270,
    Rotation.R180: Image.Transpose.ROTATE_180,
    Rotation.R270: Image.Transpose.ROTATE_90,
}


@dataclass(frozen=True, slots=True)
class FileProbe:
    format: str | None
    """Pillow format id, or None if the file cannot be opened (the image source then reports why)."""
    embedded: RGBImage | None
    """The usable EXIF thumbnail, oriented and in sRGB, or None."""


def probe(path: Path, rotation: Rotation) -> FileProbe:
    """Reads the file header and, for JPEG, the EXIF thumbnail if it is large enough. Never raises."""
    try:
        with Image.open(path) as image:
            fmt = image.format
            if fmt not in REDUCED_DECODE_FORMATS:
                return FileProbe(fmt, None)
            embedded = _embedded(image, rotation)
    except Exception as exc:  # Pillow raises many types on malformed files
        _log.debug("Cannot probe %s: %s", path, exc)
        return FileProbe(None, None)
    return FileProbe(fmt, embedded)


def _embedded(image: Image.Image, rotation: Rotation) -> RGBImage | None:
    raw = image.info.get("exif")
    if not isinstance(raw, bytes) or not raw:
        return None
    try:
        exif = image.getexif()
        ifd1 = exif.get_ifd(ExifTags.IFD.IFD1)
        offset = ifd1.get(_THUMBNAIL_OFFSET_TAG)
        length = ifd1.get(_THUMBNAIL_LENGTH_TAG)
        if not isinstance(offset, int) or not isinstance(length, int) or offset <= 0 or length <= 0:
            return None
        tiff = raw[len(_EXIF_HEADER) :] if raw.startswith(_EXIF_HEADER) else raw
        data = tiff[offset : offset + length]
        if len(data) != length or not data.startswith(b"\xff\xd8"):
            return None
        orientation = exif.get(_ORIENTATION_TAG, 1)
        with Image.open(io.BytesIO(data), formats=("JPEG",)) as thumb:
            if not _usable(thumb.size, image.size):
                return None
            thumb.load()  # pyright: ignore[reportUnknownMemberType]
            pixels = to_srgb(
                thumb if thumb.mode in ("RGB", "L", "CMYK") else thumb.convert("RGB"),
                embedded_icc(image.info),
            )
    except Exception as exc:  # malformed EXIF or thumbnail: fall back to decoding the photo
        _log.debug("Unusable EXIF thumbnail: %s", exc)
        return None
    transpose = _EXIF_TRANSPOSE.get(orientation if isinstance(orientation, int) else 1)
    if transpose is not None:
        pixels = pixels.transpose(transpose)
    manual = _ROTATION_TRANSPOSE.get(rotation)
    if manual is not None:
        pixels = pixels.transpose(manual)
    array: Any = np.asarray(pixels, dtype=np.uint8)
    result: RGBImage = np.ascontiguousarray(array)
    return result


def _usable(thumb_size: tuple[int, int], photo_size: tuple[int, int]) -> bool:
    """Large enough and with the photo's proportions (both sizes as stored, before orientation)."""
    (tw, th), (pw, ph) = thumb_size, photo_size
    if max(tw, th) < EXIF_THUMBNAIL_MIN_SIZE or min(tw, th, pw, ph) <= 0:
        return False
    thumb_aspect, photo_aspect = tw / th, pw / ph
    # One pixel of rounding is always accepted.
    tolerance = max(EXIF_THUMBNAIL_ASPECT_TOLERANCE, 1.0 / min(tw, th))
    return abs(thumb_aspect / photo_aspect - 1.0) <= tolerance
