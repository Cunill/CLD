"""Safe file names for the downloaded songs (contract §15, ESPECIFICACIO §1.7 bis "Nom del fitxer").

The rules live in passimaker.common.files since block C09 (shared with the recordings); here only
the name used when a title has nothing usable left.
"""

from __future__ import annotations

from pathlib import Path

from passimaker.common import files
from passimaker.common.files import (
    EXTENSION,
    MAX_NAME_BYTES,
    MAX_NAME_UNITS,
    MIN_NAME_UNITS,
    WINDOWS_MAX_PATH,
)

FALLBACK_NAME = "YouTube"
"""For a title with nothing usable left (only reserved characters or dots)."""

__all__ = [
    "EXTENSION",
    "FALLBACK_NAME",
    "MAX_NAME_BYTES",
    "MAX_NAME_UNITS",
    "MIN_NAME_UNITS",
    "WINDOWS_MAX_PATH",
    "safe_name",
    "safe_target_path",
]


def safe_target_path(folder: Path, title: str) -> Path:
    """passimaker.common.files.safe_target_path, with "YouTube" for a title with nothing usable."""
    return files.safe_target_path(folder, title, fallback=FALLBACK_NAME)


def safe_name(title: str, max_units: int = MAX_NAME_UNITS) -> str:
    return files.safe_name(title, max_units, fallback=FALLBACK_NAME)
