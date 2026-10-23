"""What a drop of files on the window means: a project to open, songs, or photos (§1.1, §1.7, §1.10)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from passimaker.projectio import EXTENSION
from passimaker.ui.music_strip import is_audio


@dataclass(frozen=True, slots=True)
class DroppedFiles:
    projects: tuple[Path, ...]
    songs: tuple[Path, ...]
    photos: tuple[Path, ...]
    """Photos and folders: the importer decides what it can read."""


def sort_dropped(paths: Sequence[Path]) -> DroppedFiles:
    projects = tuple(p for p in paths if p.suffix.lower() == EXTENSION and not p.is_dir())
    songs = tuple(p for p in paths if is_audio(p) and not p.is_dir())
    taken = set(projects) | set(songs)
    return DroppedFiles(projects, songs, tuple(p for p in paths if p not in taken))
