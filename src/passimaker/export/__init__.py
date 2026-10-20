"""M11 · Export to MP4 (block B9)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from passimaker.common import CancelToken
from passimaker.model.types import Project


class ExportStatus(Enum):
    DONE = "done"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ExportResult:
    status: ExportStatus
    reason_key: str | None
    """Translatable message key when status is ERROR."""
    duration_s: float
    size_bytes: int


type ExportProgress = Callable[[float, float | None], None]
"""Called as progress(fraction 0-1, seconds_remaining or None)."""


def export_project(
    project: Project,
    dest: Path,
    *,
    progress: ExportProgress | None = None,
    cancel: CancelToken | None = None,
    sentinel: bool = False,
) -> ExportResult:
    """Validates, renders audio, composes frames and encodes. Writes to a temporary name and
    renames at the end; never leaves a partial file. `sentinel` is for tests only."""
    raise NotImplementedError("B9")
