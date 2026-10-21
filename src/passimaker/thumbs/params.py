"""Technical parameters of the thumbnail service (not user settings, so not in model.defaults)."""

from __future__ import annotations

THUMBNAIL_SIZE = 256
"""Long side of a thumbnail in pixels (smaller only if the photo, or its EXIF thumbnail, is smaller)."""

INTERMEDIATE_SIZE = 1600
"""Long side of an intermediate image in pixels (smaller only if the photo is smaller)."""

DEFAULT_DISK_LIMIT_BYTES = 2 * 1024 * 1024 * 1024

EXIF_THUMBNAIL_MIN_SIZE = 160
"""An embedded EXIF thumbnail is used when its long side is at least this."""

EXIF_THUMBNAIL_ASPECT_TOLERANCE = 0.02
"""Relative aspect difference allowed between the EXIF thumbnail and the photo. Larger means the
thumbnail has black bars (e.g. 160×120 for a 3:2 photo) or is from before an edit, so it is not used."""

REDUCED_DECODE_FORMATS = frozenset({"JPEG", "MPO"})
"""Formats that decode directly at a reduced size. For the others the whole photo is decoded
anyway, so the intermediate is made at the same time as the thumbnail."""

THUMBNAIL_JPEG_QUALITY = 90
INTERMEDIATE_JPEG_QUALITY = 92

DEFAULT_WORKERS = 2
"""Background threads that make thumbnails."""

CACHE_FORMAT_VERSION = 1
"""Part of every cache file name: changing how files are made invalidates the old ones."""
