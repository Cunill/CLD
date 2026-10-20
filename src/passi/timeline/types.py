"""Timeline data types (docs/CONTRACTES.md §5)."""

from __future__ import annotations

from dataclasses import dataclass

from passi.model import defaults


@dataclass(frozen=True, slots=True)
class Interval:
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class PhotoSlot:
    """Times in seconds from the start of the show.

    slot_*: the photo's own span (its duration); slots are contiguous and sum to the total.
    visible_*: span where the photo is on screen (slot widened by half of each crossfade).
    """

    photo_id: str
    index: int
    slot_start: float
    slot_end: float
    visible_start: float
    visible_end: float
    fade_in: Interval | None
    fade_out: Interval | None


@dataclass(frozen=True, slots=True)
class AudioSegment:
    song_id: str
    video_start: float
    video_end: float
    source_start: float
    """Position in the original file where this segment starts (after trim)."""
    fade_in_s: float
    fade_out_s: float


@dataclass(frozen=True, slots=True)
class AudioPlan:
    segments: tuple[AudioSegment, ...]
    final_fade: Interval | None
    """Volume fade applied when the music is longer than the show (ends at the total)."""


@dataclass(frozen=True, slots=True)
class Timeline:
    fps: int
    total_duration_s: float
    total_frames: int
    slots: tuple[PhotoSlot, ...]
    fade_from_black: Interval | None
    fade_to_black: Interval | None
    audio_plan: AudioPlan
    music_duration_s: float


@dataclass(frozen=True, slots=True)
class VisibleLayer:
    photo_id: str
    opacity: float
    motion_progress: float
    """0 at the start of the photo's visible span, 1 at its end."""


@dataclass(frozen=True, slots=True)
class Visibles:
    layers: tuple[VisibleLayer, ...]
    """At most two layers, bottom first."""
    black_level: float
    """0 = no black overlay, 1 = fully black (fade from/to black)."""


@dataclass(frozen=True, slots=True)
class DurationLimits:
    minimum: float = defaults.PHOTO_DURATION_RANGE.minimum
    maximum: float = defaults.PHOTO_DURATION_RANGE.maximum
    warn_below: float = defaults.FIT_TO_MUSIC_MIN_DURATION_WARNING_S


DEFAULT_DURATION_LIMITS = DurationLimits()


@dataclass(frozen=True, slots=True)
class FitResult:
    durations: tuple[float, ...]
    warning: bool
    """True when each photo would last less than DurationLimits.warn_below, or when the target
    cannot be reached within [minimum, maximum] (durations clamped; compare achieved_total_s
    with the target to tell "too many photos" from "music too long")."""
    achieved_total_s: float
