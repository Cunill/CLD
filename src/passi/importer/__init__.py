"""M2 · Photo import and metadata (block B4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from passi.common import CancelToken, ProgressCallback

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
    capture_time: datetime | None
    file_time: datetime
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


def import_paths(
    paths: Sequence[Path],
    *,
    existing: frozenset[Path] = frozenset(),
    include_subfolders: bool = False,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> ImportResult:
    """Scans files and folders, reads headers (not full images), validates and sorts."""
    raise NotImplementedError("B4")


def sort_candidates(
    candidates: Sequence[PhotoCandidate], *, by_date: bool | None = None
) -> list[PhotoCandidate]:
    """by_date=None applies the automatic rule (date if >= 80 % have EXIF date, else natural name)."""
    raise NotImplementedError("B4")
