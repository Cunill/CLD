"""M11 · Export to MP4 (block B9).

export_project() checks the files and the free space, renders the audio into a provisional WAV
(passimaker.audio), composes every frame with the shared compositor (passimaker.render, from
2 threads) and sends them to the encoder (passimaker.ffmpeg). The video is written under a
provisional name in the destination folder and renamed at the end: a cancelled or failed export
leaves no file behind. The computer does not go to sleep meanwhile.
"""

from __future__ import annotations

from passimaker.export.checks import missing_files
from passimaker.export.locations import CACHE_ENV_VAR, audio_cache_dir, cache_root
from passimaker.export.pipeline import (
    ERROR_DISK_FULL,
    ERROR_FAILED,
    ERROR_MISSING_FILES,
    ERROR_NO_PHOTOS,
    ERROR_WRITE,
    ExportResult,
    ExportStatus,
    export_project,
)
from passimaker.export.progress import ExportProgress

__all__ = [
    "CACHE_ENV_VAR",
    "ERROR_DISK_FULL",
    "ERROR_FAILED",
    "ERROR_MISSING_FILES",
    "ERROR_NO_PHOTOS",
    "ERROR_WRITE",
    "ExportProgress",
    "ExportResult",
    "ExportStatus",
    "audio_cache_dir",
    "cache_root",
    "export_project",
    "missing_files",
]
