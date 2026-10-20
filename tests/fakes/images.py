"""Synthetic ImageSource: deterministic images with the photo's aspect, no files needed."""

from __future__ import annotations

import zlib
from collections.abc import Sequence

from passimaker.common import RGBImage
from passimaker.model.types import Photo
from tests.fixtures.generate import synthetic_rgb


class SyntheticImageSource:
    """Implements passimaker.images.ImageSource. Records every request in `requests`."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, int]] = []
        self.prefetched: list[tuple[str, int]] = []

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        self.requests.append((photo.id, min_long_side))
        long_side = max(photo.width, photo.height)
        target = min(long_side, max(min_long_side, 16))
        scale = target / long_side
        width = max(1, round(photo.width * scale))
        height = max(1, round(photo.height * scale))
        return synthetic_rgb(width, height, zlib.crc32(photo.id.encode("utf-8")))

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        self.prefetched.extend((p.id, min_long_side) for p in photos)
