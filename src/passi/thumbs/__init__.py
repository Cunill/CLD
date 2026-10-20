"""M4 · Thumbnails and intermediate images on disk (block B5)."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path

from passi.common import RGBImage
from passi.images import ImageSource
from passi.model.types import Photo

THUMBNAIL_SIZE = 256
INTERMEDIATE_SIZE = 1600
DEFAULT_DISK_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


class Priority(Enum):
    VISIBLE = 0
    NORMAL = 1


type ThumbnailCallback = Callable[[str, RGBImage | None], None]
"""Called as callback(photo_id, image) from a worker thread; image is None on failure."""


class ThumbnailService:
    """Generates thumbnails (256 px) and intermediates (1600 px) in background threads and
    stores them in a disk cache keyed by path + modification time + size. No Qt."""

    def __init__(
        self, cache_dir: Path, image_source: ImageSource, disk_limit_bytes: int = DEFAULT_DISK_LIMIT_BYTES
    ) -> None:
        raise NotImplementedError("B5")

    def request_thumbnail(self, photo: Photo, priority: Priority, callback: ThumbnailCallback) -> None:
        raise NotImplementedError("B5")

    def get_intermediate(self, photo: Photo) -> RGBImage:
        """Blocking; returns the 1600 px intermediate (generating it if needed)."""
        raise NotImplementedError("B5")

    def cancel_pending(self) -> None:
        raise NotImplementedError("B5")

    def close(self) -> None:
        raise NotImplementedError("B5")
