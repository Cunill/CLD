"""M3 · Image decoding and memory cache (block B4)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from passimaker.common import PassiMakerError, RGBImage
from passimaker.model.types import Photo

DEFAULT_MEMORY_BUDGET_BYTES = 768 * 1024 * 1024


class ImageDecodeError(PassiMakerError):
    """The file could not be decoded (corrupt, unsupported or missing)."""


class ImageSource(Protocol):
    """Provides oriented sRGB images at (at least) the requested size."""

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        """Returns the photo with EXIF orientation and manual rotation applied, converted to
        sRGB RGB 8-bit, with its long side >= min_long_side (or the original size if smaller)
        and at most about twice that. Raises ImageDecodeError on failure."""
        ...

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        """Starts decoding in background threads; returns immediately."""
        ...


class CachedImageSource:
    """ImageSource implementation with reduced decoding and an LRU memory budget."""

    def __init__(self, memory_budget_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES, workers: int = 2) -> None:
        raise NotImplementedError("B4")

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        raise NotImplementedError("B4")

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        raise NotImplementedError("B4")

    def close(self) -> None:
        raise NotImplementedError("B4")
