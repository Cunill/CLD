"""Project data model (docs/CONTRACTES.md, "Estructures").

All types are immutable: the project is only changed by the controller, which replaces
whole values. This enforces architecture rule 2 and makes undo/redo trivial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from passimaker.model import defaults


class OutputFormat(Enum):
    HORIZONTAL = "horizontal"  # 1920x1080
    VERTICAL = "vertical"  # 1080x1920

    @property
    def size(self) -> tuple[int, int]:
        """Output size in pixels as (width, height)."""
        return (1920, 1080) if self is OutputFormat.HORIZONTAL else (1080, 1920)


class Intensity(Enum):
    """Motion amount presets (passimaker.motion.INTENSITY_PRESETS); the project stores the amounts."""

    SOFT = "soft"
    MEDIUM = "medium"
    STRONG = "strong"


class FitMode(Enum):
    """Fit preference chosen by the user for a photo."""

    AUTO = "auto"
    FILL = "fill"
    BLUR = "blur"
    BLACK = "black"


class ResolvedFit(Enum):
    """Fit actually applied after resolving AUTO."""

    FILL = "fill"
    BLUR = "blur"
    BLACK = "black"


class MotionMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"


class MotionType(Enum):
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"
    COMBINED = "combined"
    NONE = "none"


class Rotation(Enum):
    """Manual rotation applied after EXIF orientation (proposal P2), clockwise degrees."""

    R0 = 0
    R90 = 90
    R180 = 180
    R270 = 270


@dataclass(frozen=True, slots=True)
class Window:
    """Visible window on the photo canvas.

    centre_x, centre_y: normalised (0-1) position of the window centre on the canvas.
    scale: 1.0 is the largest window of the output aspect ratio that fits in the canvas;
    larger values zoom in (the window is 1/scale of that size).
    """

    centre_x: float = 0.5
    centre_y: float = 0.5
    scale: float = 1.0


@dataclass(frozen=True, slots=True)
class PhotoMotion:
    mode: MotionMode = MotionMode.AUTO
    type: MotionType = MotionType.NONE
    draw_count: int = 0
    start: Window = field(default_factory=Window)
    end: Window = field(default_factory=Window)
    resolved_fit: ResolvedFit = ResolvedFit.FILL


@dataclass(frozen=True, slots=True)
class Photo:
    id: str
    path: Path
    relative_path: Path | None
    width: int
    """Width after applying EXIF orientation and manual rotation."""
    height: int
    exif_orientation: int = 1
    capture_time: datetime | None = None
    duration_s: float | None = None
    """None means "use the project default duration"."""
    fit: FitMode = FitMode.AUTO
    motion: PhotoMotion = field(default_factory=PhotoMotion)
    rotation: Rotation = Rotation.R0
    low_resolution: bool = False


class BlackSlidePosition(Enum):
    START = "start"
    END = "end"


BLACK_START_ID = "black:start"
BLACK_END_ID = "black:end"
"""Fixed ids of the black slides; photo ids never contain ":" (M08)."""


@dataclass(frozen=True, slots=True)
class BlackSlide:
    """A black card in the storyboard (M08): always the first (START) or the last (END) slide."""

    position: BlackSlidePosition
    duration_s: float = defaults.BLACK_SLIDE_DURATION_S

    @property
    def id(self) -> str:
        return BLACK_START_ID if self.position is BlackSlidePosition.START else BLACK_END_ID


type Slide = Photo | BlackSlide


@dataclass(frozen=True, slots=True)
class Fade:
    enabled: bool
    seconds: float


@dataclass(frozen=True, slots=True)
class Song:
    id: str
    path: Path
    relative_path: Path | None
    original_duration_s: float
    trim_start_s: float = 0.0
    trim_end_s: float | None = None
    """None means "until the end of the file"."""
    fade_in: Fade = field(default_factory=lambda: Fade(True, defaults.SONG_FADE_IN_S))
    fade_out: Fade = field(default_factory=lambda: Fade(True, defaults.SONG_FADE_OUT_S))
    volume: float = defaults.SONG_VOLUME
    loudness_gain_db: float | None = None
    """Normalisation gain computed by the audio engine; None until measured."""


@dataclass(frozen=True, slots=True)
class Music:
    master_volume: float = defaults.MASTER_VOLUME
    normalize: bool = True
    keep_fitted: bool = False
    silence_start_s: float = defaults.MUSIC_SILENCE_S
    """Silence before the first song (M13): the music starts this long after the show."""
    silence_end_s: float = defaults.MUSIC_SILENCE_S
    """Silence after the music (M13): the music ends at least this long before the show."""
    songs: tuple[Song, ...] = ()


@dataclass(frozen=True, slots=True)
class Project:
    name: str = ""
    format_version: int = defaults.FORMAT_VERSION
    output_format: OutputFormat = OutputFormat.HORIZONTAL
    seed: int = 0
    default_duration_s: float = defaults.PHOTO_DURATION_S
    crossfade_s: float = defaults.CROSSFADE_S
    fade_from_black_s: float = defaults.FADE_FROM_BLACK_S
    fade_to_black_s: float = defaults.FADE_TO_BLACK_S
    motion_enabled: bool = True
    zoom_amount: float = defaults.ZOOM_AMOUNT
    pan_amount: float = defaults.PAN_AMOUNT
    slides: tuple[Slide, ...] = ()
    """Storyboard order: an optional START black slide, the photos, an optional END black slide (M08).
    The editing commands keep the black slides at the ends."""
    music: Music = field(default_factory=Music)
    photos: tuple[Photo, ...] = field(init=False, repr=False, compare=False)
    """The photos of `slides`, in order (derived)."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "photos", tuple(s for s in self.slides if isinstance(s, Photo)))

    @property
    def black_start(self) -> BlackSlide | None:
        first = self.slides[0] if self.slides else None
        return first if isinstance(first, BlackSlide) and first.position is BlackSlidePosition.START else None

    @property
    def black_end(self) -> BlackSlide | None:
        last = self.slides[-1] if self.slides else None
        return last if isinstance(last, BlackSlide) and last.position is BlackSlidePosition.END else None

    def photo_duration(self, photo: Slide) -> float:
        """Effective duration of a slide (its own, or the project default for a photo without one)."""
        return photo.duration_s if photo.duration_s is not None else self.default_duration_s


def new_project(**settings: Any) -> Project:
    """A new project: the given settings and the two black slides (M08). `Project()` has none."""
    slides = (BlackSlide(BlackSlidePosition.START), BlackSlide(BlackSlidePosition.END))
    return Project(slides=slides, **settings)
