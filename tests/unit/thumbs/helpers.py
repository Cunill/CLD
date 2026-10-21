"""Helpers shared by the B5 thumbnail tests."""

from __future__ import annotations

import io
import shutil
import struct
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from passimaker.common import RGBImage
from passimaker.images import CachedImageSource
from passimaker.model.types import Photo
from tests.unit.images.helpers import photo_for

__all__ = [
    "Collector",
    "RecordingSource",
    "copies",
    "exif_with_thumbnail",
    "photo_for",
    "pseudo_photo",
    "write_jpeg",
]


def pseudo_photo(width: int, height: int, seed: int = 1) -> NDArray[np.uint8]:
    """Smooth gradients plus some texture: compresses like a photo, never magenta."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[..., 0] = 60 + 120 * x + 0 * y
    image[..., 1] = 110 + 80 * y + 0 * x
    image[..., 2] = 50 + 50 * (x + y)
    noise = rng.integers(0, 12, size=(height, width, 1), dtype=np.uint8)
    image += noise
    return image


def _jpeg_bytes(image: NDArray[np.uint8], quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def exif_with_thumbnail(
    thumbnail: NDArray[np.uint8] | None, orientation: int = 1, *, big_endian: bool = False
) -> bytes:
    """APP1 EXIF data with IFD0 (orientation) and, if given, an IFD1 JPEG thumbnail, as cameras write it."""
    order = ">" if big_endian else "<"
    data = _jpeg_bytes(thumbnail) if thumbnail is not None else b""
    tiff = (b"MM\x00*" if big_endian else b"II*\x00") + struct.pack(order + "I", 8)
    ifd1_offset = 8 + 18 if thumbnail is not None else 0
    tiff += struct.pack(order + "H", 1)
    tiff += struct.pack(order + "HHIHH", 0x0112, 3, 1, orientation, 0)
    tiff += struct.pack(order + "I", ifd1_offset)
    if thumbnail is not None:
        data_offset = ifd1_offset + 2 + 3 * 12 + 4
        tiff += struct.pack(order + "H", 3)
        tiff += struct.pack(order + "HHIHH", 0x0103, 3, 1, 6, 0)
        tiff += struct.pack(order + "HHII", 0x0201, 4, 1, data_offset)
        tiff += struct.pack(order + "HHII", 0x0202, 4, 1, len(data))
        tiff += struct.pack(order + "I", 0)
        tiff += data
    return b"Exif\x00\x00" + tiff


def write_jpeg(path: Path, image: NDArray[np.uint8], exif: bytes | None = None, quality: int = 90) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exif is None:
        Image.fromarray(image).save(path, "JPEG", quality=quality)
    else:
        Image.fromarray(image).save(path, "JPEG", quality=quality, exif=exif)
    return path


def copies(source: Path, folder: Path, count: int, prefix: str = "foto") -> list[Path]:
    """`count` different files with the same contents (the cache identifies files by path)."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = [folder / f"{prefix}_{i:04d}{source.suffix}" for i in range(count)]
    for path in paths:
        shutil.copyfile(source, path)
    return paths


class RecordingSource:
    """ImageSource that records requests, can hold the first one and can be slowed down."""

    def __init__(self, *, hold_first: bool = False, delay_s: float = 0.0) -> None:
        self._inner = CachedImageSource(memory_budget_bytes=64 * 1024 * 1024, workers=1)
        self._lock = threading.Lock()
        self.calls: list[tuple[str, int]] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        if not hold_first:
            self.release.set()
        self._delay_s = delay_s

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        with self._lock:
            self.calls.append((photo.id, min_long_side))
        self.entered.set()
        self.release.wait(10)
        if self._delay_s:
            time.sleep(self._delay_s)
        return self._inner.get_image(photo, min_long_side)

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        pass

    def close(self) -> None:
        self.release.set()
        self._inner.close()


class Collector:
    """Thumbnail callback that records the results and the thread they arrive on."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.results: dict[str, RGBImage | None] = {}
        self.order: list[str] = []
        self.threads: set[int] = set()
        self.done = threading.Event()
        self.expected = 0

    def __call__(self, photo_id: str, image: RGBImage | None) -> None:
        with self._lock:
            self.results[photo_id] = image
            self.order.append(photo_id)
            self.threads.add(threading.get_ident())
            if self.expected and len(self.order) >= self.expected:
                self.done.set()

    def wait(self, count: int, timeout: float = 30.0) -> bool:
        with self._lock:
            self.expected = count
            if len(self.order) >= count:
                return True
        return self.done.wait(timeout)
