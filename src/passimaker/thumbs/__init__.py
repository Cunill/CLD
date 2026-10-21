"""M4 · Thumbnails and intermediate images on disk (block B5).

Public API (docs/CONTRACTES.md §4): ThumbnailService, Priority, ThumbnailCallback, THUMBNAIL_SIZE,
INTERMEDIATE_SIZE and DEFAULT_DISK_LIMIT_BYTES. passimaker.render imports INTERMEDIATE_SIZE from
here, so this package must stay free of import side effects and must not import render or export.
"""

from __future__ import annotations

from passimaker.thumbs.params import DEFAULT_DISK_LIMIT_BYTES, INTERMEDIATE_SIZE, THUMBNAIL_SIZE
from passimaker.thumbs.service import Priority, ThumbnailCallback, ThumbnailService

__all__ = [
    "DEFAULT_DISK_LIMIT_BYTES",
    "INTERMEDIATE_SIZE",
    "THUMBNAIL_SIZE",
    "Priority",
    "ThumbnailCallback",
    "ThumbnailService",
]
