"""Builders shared by the model tests (invented photo metadata; no real images)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from passimaker import timeline
from passimaker.model import ProjectController
from passimaker.model.commands import AddPhotos, AddSongs
from passimaker.model.types import Photo, Project, Song

FOLDER = Path("/fotos")


def photo(
    pid: str,
    width: int = 4000,
    height: int = 3000,
    *,
    name: str | None = None,
    duration: float | None = None,
    taken: datetime | None = None,
) -> Photo:
    return Photo(
        pid, FOLDER / (name or f"{pid}.jpg"), None, width, height, capture_time=taken, duration_s=duration
    )


def photos(count: int, prefix: str = "p") -> tuple[Photo, ...]:
    return tuple(photo(f"{prefix}{i:03d}") for i in range(count))


def song(sid: str, seconds: float = 60.0, **changes: object) -> Song:
    return Song(sid, FOLDER / f"{sid}.mp3", None, seconds, **changes)  # type: ignore[arg-type]


def controller_with(count: int, seed: int = 7, songs: Sequence[Song] = ()) -> ProjectController:
    controller = ProjectController(Project(seed=seed))
    if count:
        controller.execute(AddPhotos(photos(count)))
    if songs:
        controller.execute(AddSongs(tuple(songs)))
    controller.replace_project(controller.project)
    return controller


def ids(project: Project) -> list[str]:
    return [p.id for p in project.photos]


def proportional_fit(
    durations: Sequence[float],
    target_s: float,
    limits: timeline.DurationLimits = timeline.DEFAULT_DURATION_LIMITS,
) -> timeline.FitResult:
    """Stand-in for timeline.fit_to_music (block B2, developed in parallel)."""
    factor = target_s / sum(durations)
    fitted = tuple(min(limits.maximum, max(limits.minimum, d * factor)) for d in durations)
    warning = any(d * factor < limits.warn_below for d in durations)
    return timeline.FitResult(fitted, warning, sum(fitted))
