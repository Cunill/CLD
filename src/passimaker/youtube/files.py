"""Safe file names for the downloaded songs (block C03)."""

from __future__ import annotations

from pathlib import Path


def safe_target_path(folder: Path, title: str) -> Path:
    """A free path `<folder>/<title>.mp3`, valid on Windows; `<title> (2).mp3`… if taken.

    Never an existing file.
    """
    raise NotImplementedError("passimaker.youtube: implemented in block C03")
