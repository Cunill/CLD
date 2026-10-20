"""Editing commands (docs/CONTRACTES.md, "Ordres del controlador").

Commands are plain data. The controller (block B1) applies them to the current project and
keeps the previous snapshots for undo/redo (proposal P1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from passi.model.types import (
    FitMode,
    Intensity,
    MotionType,
    OutputFormat,
    Photo,
    Rotation,
    Song,
)


class Change(Enum):
    """What kind of data changed; observers use it to decide what to refresh."""

    PHOTOS = "photos"  # list of photos (added, removed, reordered, duplicated)
    TIMING = "timing"  # durations, fades
    MOTION = "motion"  # motions, fits, motion amounts, output format
    MUSIC = "music"  # songs and audio settings
    SETTINGS = "settings"  # other project settings (name...)
    SAVED_STATE = "saved_state"  # "unsaved changes" flag


@dataclass(frozen=True, slots=True)
class AddPhotos:
    photos: tuple[Photo, ...]
    index: int | None = None
    """Insertion position; None appends at the end."""


@dataclass(frozen=True, slots=True)
class RemovePhotos:
    photo_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class MovePhotos:
    photo_ids: tuple[str, ...]
    target_index: int
    """Index in the list *before* the move where the moved block is inserted."""


@dataclass(frozen=True, slots=True)
class DuplicatePhotos:
    photo_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SortPhotos:
    by_date: bool
    """True sorts by capture date, False by natural file name order."""


@dataclass(frozen=True, slots=True)
class SetDefaultDuration:
    seconds: float


@dataclass(frozen=True, slots=True)
class SetPhotoDuration:
    photo_ids: frozenset[str]
    seconds: float | None
    """None resets the photos to the project default."""


@dataclass(frozen=True, slots=True)
class SetPhotoFit:
    photo_ids: frozenset[str]
    fit: FitMode


@dataclass(frozen=True, slots=True)
class SetPhotoMotion:
    photo_ids: frozenset[str]
    motion_type: MotionType | None
    """A type fixes the motion (manual mode); None returns the photos to automatic mode."""


@dataclass(frozen=True, slots=True)
class RerollMotions:
    photo_ids: frozenset[str] | None
    """Photos to draw again; None means every photo in automatic mode."""


@dataclass(frozen=True, slots=True)
class RotatePhotos:
    photo_ids: frozenset[str]
    rotation: Rotation
    """Clockwise turn added to each photo's current rotation (R90 = right, R270 = left)."""


@dataclass(frozen=True, slots=True)
class SetProjectSettings:
    """Any field left as None is not changed."""

    name: str | None = None
    output_format: OutputFormat | None = None
    crossfade_s: float | None = None
    fade_from_black_s: float | None = None
    fade_to_black_s: float | None = None
    motion_enabled: bool | None = None
    intensity: Intensity | None = None
    """Preset: sets zoom_amount and pan_amount (passi.motion.INTENSITY_PRESETS)."""
    zoom_amount: float | None = None
    pan_amount: float | None = None


@dataclass(frozen=True, slots=True)
class AddSongs:
    songs: tuple[Song, ...]
    index: int | None = None


@dataclass(frozen=True, slots=True)
class RemoveSongs:
    song_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class MoveSongs:
    song_ids: tuple[str, ...]
    target_index: int


@dataclass(frozen=True, slots=True)
class UpdateSong:
    """Replaces a song's settings (trims, fades, volume) by the given value with the same id."""

    song: Song


@dataclass(frozen=True, slots=True)
class SetMusicSettings:
    master_volume: float | None = None
    normalize: bool | None = None
    keep_fitted: bool | None = None


@dataclass(frozen=True, slots=True)
class FitToMusic:
    """Rescale photo durations so the show lasts as long as the music."""


Command = (
    AddPhotos
    | RemovePhotos
    | MovePhotos
    | DuplicatePhotos
    | SortPhotos
    | SetDefaultDuration
    | SetPhotoDuration
    | SetPhotoFit
    | SetPhotoMotion
    | RerollMotions
    | RotatePhotos
    | SetProjectSettings
    | AddSongs
    | RemoveSongs
    | MoveSongs
    | UpdateSong
    | SetMusicSettings
    | FitToMusic
)
