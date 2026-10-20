"""Data types of the importer (docs/CONTRACTES.md §2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
)
RAW_EXTENSIONS: frozenset[str] = frozenset(
    {".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf", ".pef", ".srw"}
)


class ImportFailure(Enum):
    UNSUPPORTED = "unsupported"
    RAW = "raw"
    CORRUPT = "corrupt"
    TOO_SMALL = "too_small"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class PhotoCandidate:
    path: Path
    width: int
    """Already oriented (EXIF applied)."""
    height: int
    exif_orientation: int
    """Orientation applied when decoding (1 for HEIF and TIFF, whose readers already apply it)."""
    capture_time: datetime | None
    """EXIF DateTimeOriginal (or DateTimeDigitized), with sub-seconds; naive local time."""
    file_time: datetime
    """Modification time of the file; naive local time."""
    color_profile: str | None
    """Description of the embedded ICC profile, or None for sRGB / no profile."""


@dataclass(frozen=True, slots=True)
class FailedFile:
    path: Path
    reason: ImportFailure


@dataclass(frozen=True, slots=True)
class ImportResult:
    candidates: tuple[PhotoCandidate, ...]
    """Sorted as described in docs/ESPECIFICACIO.md §1.1."""
    failures: tuple[FailedFile, ...]
    duplicates: tuple[Path, ...]
    """Files already present in `existing` (they are NOT in candidates)."""
    subfolder_photo_count: int
    """Photos found in subfolders that were not imported (to ask the user)."""
    cancelled: bool
