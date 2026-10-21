"""Checks before exporting (ESPECIFICACIO §1.9): files that are not found and free disk space."""

from __future__ import annotations

import shutil
from pathlib import Path

from passimaker.audio import CHANNELS, SAMPLE_RATE
from passimaker.export.files import is_file, long_path
from passimaker.export.params import DISK_MARGIN_BYTES, VIDEO_BYTES_PER_S
from passimaker.model.types import Project

WAV_BYTES_PER_S = SAMPLE_RATE * CHANNELS * 2
"""16-bit PCM (passimaker.audio render_wav)."""


def missing_files(project: Project) -> tuple[Path, ...]:
    """Photos and songs of the project that are not found, in project order, without repetitions.

    When this is not empty the export does not start; the interface shows the list (§1.9).
    """
    paths = [photo.path for photo in project.photos] + [song.path for song in project.music.songs]
    return tuple(path for path in dict.fromkeys(paths) if not is_file(path))


def estimated_video_bytes(duration_s: float) -> int:
    return round(duration_s * VIDEO_BYTES_PER_S)


def wav_bytes(duration_s: float) -> int:
    return round(duration_s * WAV_BYTES_PER_S)


def free_bytes(folder: Path) -> int:
    return shutil.disk_usage(long_path(folder)).free


def has_room(folder: Path, needed_bytes: int) -> bool:
    """True when `folder` has space for `needed_bytes` plus a safety margin."""
    return free_bytes(folder) >= needed_bytes + DISK_MARGIN_BYTES
