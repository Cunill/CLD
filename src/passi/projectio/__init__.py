"""M12 · Save and open .passi project files (block B1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from passi.common import PassiError
from passi.model.types import Project

EXTENSION = ".passi"


class ProjectFileError(PassiError):
    """Corrupt file, unknown newer format version, or I/O error."""


@dataclass(frozen=True, slots=True)
class OpenResult:
    project: Project
    missing_files: tuple[Path, ...]


def save_project(project: Project, path: Path) -> None:
    """Atomic write (temporary file + rename). Stores relative and absolute paths."""
    raise NotImplementedError("B1")


def open_project(path: Path) -> OpenResult:
    raise NotImplementedError("B1")


def relink(project: Project, folder: Path) -> tuple[Project, int]:
    """Finds missing photos/songs by file name inside folder; returns (project, relinked count)."""
    raise NotImplementedError("B1")


def save_recovery(project: Project, recovery_dir: Path) -> Path:
    raise NotImplementedError("B1")


def find_recovery(recovery_dir: Path) -> Path | None:
    raise NotImplementedError("B1")


def clear_recovery(recovery_dir: Path) -> None:
    raise NotImplementedError("B1")
