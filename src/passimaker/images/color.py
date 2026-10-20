"""Colour management: embedded profiles to sRGB (LittleCMS through Pillow's ImageCms).

Photos may carry an ICC profile (Display P3 from iPhones, Adobe RGB from cameras, CMYK from
print workflows) or, in HEIF files, an "nclx" description of their primaries. Everything is
converted to sRGB so that colours do not look washed out.
"""

from __future__ import annotations

import io
import struct
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from PIL import Image, ImageCms

type Chromaticity = tuple[float, float]

D65: Chromaticity = (0.3127, 0.3290)
D50_XYZ: tuple[float, float, float] = (0.9642, 1.0, 0.8249)
SRGB_PRIMARIES: tuple[Chromaticity, Chromaticity, Chromaticity] = ((0.64, 0.33), (0.30, 0.60), (0.15, 0.06))
DISPLAY_P3_PRIMARIES: tuple[Chromaticity, Chromaticity, Chromaticity] = (
    (0.680, 0.320),
    (0.265, 0.690),
    (0.150, 0.060),
)
SRGB_TRC: tuple[float, float, float, float, float] = (2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045)
"""Parameters (g, a, b, c, d) of the ICC parametric curve type 3 that matches the sRGB curve."""

NCLX_PRIMARIES_BT709 = 1
NCLX_PRIMARIES_DISPLAY_P3 = 12
NCLX_SRGB_LIKE_TRANSFERS = frozenset({1, 6, 13, 14, 15})
"""H.273 transfer characteristics close enough to the sRGB curve (BT.709, BT.601, sRGB, BT.2020 SDR)."""

_BRADFORD = np.array(
    [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]], dtype=np.float64
)
_TRANSFORM_CACHE_SIZE = 32


def _xyz(xy: Chromaticity) -> np.ndarray[Any, np.dtype[np.float64]]:
    x, y = xy
    return np.array([x / y, 1.0, (1.0 - x - y) / y], dtype=np.float64)


def rgb_to_xyz_d50(
    primaries: Sequence[Chromaticity], white: Chromaticity = D65
) -> np.ndarray[Any, np.dtype[np.float64]]:
    """3×3 matrix from linear RGB to XYZ, adapted to D50 (the ICC connection space) with Bradford."""
    columns = np.stack([_xyz(p) for p in primaries], axis=1)
    scale = np.linalg.solve(columns, _xyz(white))
    to_xyz = columns * scale
    cone_src = _BRADFORD @ _xyz(white)
    cone_dst = _BRADFORD @ np.array(D50_XYZ, dtype=np.float64)
    adapt = np.linalg.inv(_BRADFORD) @ np.diag(cone_dst / cone_src) @ _BRADFORD
    return adapt @ to_xyz


def _s15f16(value: float) -> bytes:
    return struct.pack(">i", round(value * 65536))


def _xyz_tag(xyz: Sequence[float]) -> bytes:
    return b"XYZ \0\0\0\0" + b"".join(_s15f16(v) for v in xyz)


def _desc_tag(text: str) -> bytes:
    ascii_text = text.encode("ascii", "replace") + b"\0"
    return (
        b"desc\0\0\0\0"
        + struct.pack(">I", len(ascii_text))
        + ascii_text
        + struct.pack(">II", 0, 0)
        + struct.pack(">HB", 0, 0)
        + bytes(67)
    )


def _text_tag(text: str) -> bytes:
    return b"text\0\0\0\0" + text.encode("ascii", "replace") + b"\0"


def _trc_tag(trc: float | Sequence[float]) -> bytes:
    if isinstance(trc, float | int):
        return b"curv\0\0\0\0" + struct.pack(">IH", 1, round(float(trc) * 256))
    params = tuple(trc)
    return b"para\0\0\0\0" + struct.pack(">HH", 3, 0) + b"".join(_s15f16(v) for v in params)


def rgb_profile_bytes(
    description: str,
    primaries: Sequence[Chromaticity],
    trc: float | Sequence[float] = SRGB_TRC,
    white: Chromaticity = D65,
) -> bytes:
    """A minimal ICC v2 matrix/TRC display profile. `trc` is a gamma or the 5 sRGB-style parameters."""
    matrix = rgb_to_xyz_d50(primaries, white)
    curve = _trc_tag(trc)
    tags: list[tuple[bytes, bytes]] = [
        (b"desc", _desc_tag(description)),
        (b"cprt", _text_tag("No copyright, use freely")),
        (b"wtpt", _xyz_tag(D50_XYZ)),
        (b"rXYZ", _xyz_tag(matrix[:, 0].tolist())),
        (b"gXYZ", _xyz_tag(matrix[:, 1].tolist())),
        (b"bXYZ", _xyz_tag(matrix[:, 2].tolist())),
        (b"rTRC", curve),
        (b"gTRC", curve),
        (b"bTRC", curve),
    ]
    table_size = 4 + 12 * len(tags)
    offset = 128 + table_size
    table = struct.pack(">I", len(tags))
    data = b""
    for signature, payload in tags:
        padded = payload + bytes(-len(payload) % 4)
        table += signature + struct.pack(">II", offset + len(data), len(payload))
        data += padded
    size = 128 + table_size + len(data)
    header = (
        struct.pack(">I", size)
        + bytes(4)
        + struct.pack(">I", 0x02100000)
        + b"mntrRGB XYZ "
        + struct.pack(">6H", 2026, 1, 1, 0, 0, 0)
        + b"acsp"
        + bytes(4)
        + struct.pack(">I", 0)
        + bytes(4)
        + struct.pack(">I", 0)
        + bytes(8)
        + struct.pack(">I", 0)
        + b"".join(_s15f16(v) for v in D50_XYZ)
        + bytes(4)
    )
    header += bytes(128 - len(header))
    return header + table + data


DISPLAY_P3_ICC = rgb_profile_bytes("Display P3 (nclx)", DISPLAY_P3_PRIMARIES)
"""Used for HEIF files that describe Display P3 with an nclx box instead of an ICC profile."""


def nclx_icc(nclx: Mapping[str, Any] | None) -> bytes | None:
    """ICC profile equivalent to an HEIF nclx description, or None if it is sRGB or unknown."""
    if not nclx:
        return None
    primaries = nclx.get("color_primaries")
    transfer = nclx.get("transfer_characteristics")
    if primaries == NCLX_PRIMARIES_DISPLAY_P3 and transfer in NCLX_SRGB_LIKE_TRANSFERS:
        return DISPLAY_P3_ICC
    return None


def embedded_icc(info: Mapping[Any, Any]) -> bytes | None:
    """The ICC profile of an open image (from `Image.info`), including HEIF nclx descriptions."""
    icc = info.get("icc_profile")
    if isinstance(icc, bytes) and icc:
        return icc
    nclx = info.get("nclx_profile")
    return nclx_icc(nclx if isinstance(nclx, Mapping) else None)  # pyright: ignore[reportUnknownArgumentType]


def profile_description(icc: bytes) -> str | None:
    """Description of an ICC profile; None if it is sRGB. Unreadable profiles are "?"."""
    try:
        description = ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip()
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError):
        return "?"
    if "srgb" in description.casefold():
        return None
    return description or "?"


_SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
_transforms: OrderedDict[tuple[bytes, str], ImageCms.ImageCmsTransform | None] = OrderedDict()
_transforms_lock = threading.Lock()


def _transform(icc: bytes, mode: str) -> ImageCms.ImageCmsTransform | None:
    """Cached transform to sRGB; None for sRGB profiles and for profiles that cannot be used."""
    key = (icc, mode)
    with _transforms_lock:
        if key in _transforms:
            _transforms.move_to_end(key)
            return _transforms[key]
    transform: ImageCms.ImageCmsTransform | None = None
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if "srgb" not in ImageCms.getProfileDescription(source).casefold():
            # NOCACHE: the same transform is applied from several decoding threads at once.
            transform = ImageCms.buildTransform(
                source,
                _SRGB,
                mode,
                "RGB",
                ImageCms.Intent.RELATIVE_COLORIMETRIC,
                ImageCms.Flags.NOCACHE | ImageCms.Flags.BLACKPOINTCOMPENSATION,
            )
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError):
        transform = None
    with _transforms_lock:
        _transforms[key] = transform
        while len(_transforms) > _TRANSFORM_CACHE_SIZE:
            _transforms.popitem(last=False)
    return transform


def to_srgb(image: Image.Image, icc: bytes | None) -> Image.Image:
    """Converts an "RGB", "L" or "CMYK" image to sRGB "RGB" using its profile when there is one.

    Without a profile (or with sRGB, or with a profile that LittleCMS rejects) the values are
    taken as sRGB and only the mode is converted.
    """
    transform = _transform(icc, image.mode) if icc else None
    if transform is not None:
        try:
            return ImageCms.applyTransform(image, transform) or image
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return image if image.mode == "RGB" else image.convert("RGB")
