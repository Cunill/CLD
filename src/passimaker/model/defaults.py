"""Default values and allowed ranges (docs/ESPECIFICACIO.md, "Valors per defecte globals").

This is the single place where user-facing defaults live, so they can be tuned after the
manual reviews (milestones F1-F3) without touching any other module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Range:
    minimum: float
    maximum: float
    step: float

    def clamp(self, value: float) -> float:
        return min(self.maximum, max(self.minimum, value))


FORMAT_VERSION = 1
FPS = 30

PHOTO_DURATION_S = 2.0
PHOTO_DURATION_RANGE = Range(0.4, 24.0, 0.1)
"""What can be set by hand (M05, user request); the timeline shortens the crossfade of a short photo."""
FIT_TO_MUSIC_DURATION_RANGE = Range(1.0, 3.0, 0.1)
"""What "Ajustar a la música" may give each photo (decision 0005): shorter photos would be dizzying."""

CROSSFADE_S = 1.0
CROSSFADE_RANGE = Range(0.5, 1.5, 0.1)

FADE_FROM_BLACK_S = 1.0
FADE_TO_BLACK_S = 2.0
BLACK_FADE_RANGE = Range(0.0, 5.0, 0.1)

ZOOM_AMOUNT = 0.09
"""Zoom per photo (0.09 = the image grows or shrinks 9 % while it is visible). Decision 0005."""
PAN_AMOUNT = 0.09
"""Displacement per photo, as a fraction of the visible window side. Decision 0005."""
MOTION_AMOUNT_RANGE = Range(0.0, 0.20, 0.01)

SONG_FADE_IN_S = 1.0
SONG_FADE_OUT_S = 3.0
SONG_FADE_RANGE = Range(0.0, 10.0, 0.5)
MUSIC_FINAL_FADE_S = 3.0
CUT_MICRO_FADE_S = 0.010
SHORT_SONG_FADE_FRACTION = 0.4
SONG_TRIM_STEP_S = 0.1
"""The trim of a song goes in tenths of a second; its start stays at least this far from its end (B14)."""
"""§1.7: a song shorter than its two fades gets each fade reduced to 40 % of its length."""

MASTER_VOLUME = 1.0
MASTER_VOLUME_RANGE = Range(0.0, 1.0, 0.01)
SONG_VOLUME = 1.0
SONG_VOLUME_RANGE = Range(0.0, 1.5, 0.01)
LOUDNESS_TARGET_LUFS = -16.0
LIMITER_CEILING_DBFS = -1.0

FIT_TO_MUSIC_MIN_DURATION_WARNING_S = 1.0

MAX_PHOTOS_WITHOUT_WARNING = 1000
MIN_PHOTO_SIDE_PX = 64
DATE_ORDER_MIN_FRACTION = 0.8
"""Imported photos are ordered by date when at least this fraction has an EXIF capture date (§1.1)."""

AUTOSAVE_INTERVAL_S = 120
UNDO_HISTORY_STEPS = 100
"""Undo history depth (§1.13, P1)."""
