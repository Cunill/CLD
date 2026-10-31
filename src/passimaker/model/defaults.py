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


FORMAT_VERSION = 2
"""2 (M08): black slides at the start and the end; version 1 files open without them."""
FPS = 30

PHOTO_DURATION_S = 2.0
PHOTO_DURATION_RANGE = Range(0.4, 24.0, 0.1)
"""What can be set by hand (M05, user request); the timeline shortens the crossfade of a short photo."""
BLACK_SLIDE_DURATION_S = 2.0
"""Black slides at the start and the end of a new project (M08); their duration uses PHOTO_DURATION_RANGE."""
FIT_TO_MUSIC_DURATION_RANGE = PHOTO_DURATION_RANGE
"""What "Ajustar a la música" may give each photo: the same range as by hand (decision 0014, M07)."""

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
MUSIC_SILENCE_S = 0.0
MUSIC_SILENCE_RANGE = Range(0.0, 60.0, 0.5)
"""Seconds of silence before the first song and after the music, up to the end of the show (M13)."""
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

FIT_TO_MUSIC_MIN_DURATION_WARNING_S = FIT_TO_MUSIC_DURATION_RANGE.minimum

MAX_PHOTOS_WITHOUT_WARNING = 1000
MIN_PHOTO_SIDE_PX = 64
DATE_ORDER_MIN_FRACTION = 0.8
"""Imported photos are ordered by date when at least this fraction has an EXIF capture date (§1.1)."""

AUTOSAVE_INTERVAL_S = 120
UNDO_HISTORY_STEPS = 100
"""Undo history depth (§1.13, P1)."""

YOUTUBE_RESULTS_PER_PAGE = 10
"""Results of a YouTube search shown at once; "Més resultats" loads as many again (decision 0012)."""
YOUTUBE_MAX_DURATION_S = 20 * 60.0
"""Longer videos cannot be downloaded (avoids hour-long mixes by mistake). The message says "20 minuts"."""
YOUTUBE_MP3_BITRATE_KBPS = 192
"""MP3 of the downloaded songs, 48 kHz stereo like the mixer (decision 0012)."""
YOUTUBE_SIMULTANEOUS_DOWNLOADS = 2
"""Downloads running at the same time; the rest wait in the queue."""

RECORD_START_WHEN_SOUND = True
""""Comença quan soni": after [● Grava], nothing is saved until the level first reaches the threshold."""
RECORD_START_THRESHOLD_DBFS = -50.0
"""Level (peak of any channel) that counts as sound for "Comença quan soni" (decision 0013)."""
RECORD_SILENCE_STOP_ENABLED = True
RECORD_SILENCE_STOP_S = 5.0
"""Seconds of silence after which the recording stops on its own (and is saved: StopReason.SILENCE)."""
RECORD_SILENCE_STOP_RANGE = Range(1.0, 60.0, 1.0)
RECORD_SILENCE_THRESHOLD_DBFS = -50.0
"""Below this level (every channel) the recording counts as silent, for the automatic stop."""
RECORD_TRIM_ENABLED = True
RECORD_TRIM_THRESHOLD_DBFS = -50.0
"""The silence at the start and at the end, below this level, is trimmed when the recording stops."""
RECORD_TRIM_MARGIN_S = 0.2
"""Kept before the first sound and after the last one when trimming."""
RECORD_MAX_DURATION_S = 30 * 60.0
"""On reaching it the recording is discarded (decision 0013, G5). The message says "30 minuts"."""
RECORD_MAX_WARNING_S = 60.0
"""The elapsed time turns orange this long before RECORD_MAX_DURATION_S."""
RECORD_MIN_FREE_BYTES = 1024**3
"""1 GB: with less free space in the temporary folder a recording does not start (one in progress stops)."""
RECORD_MP3_BITRATE_KBPS = 192
"""MP3 of the recorded songs, 48 kHz stereo, like YouTube's (decision 0013, G7)."""
RECORD_WAVE_WINDOW_S = 10.0
"""The live waves show the last 10 seconds (ESPECIFICACIO §1.7 ter)."""
RECORD_PEAK_COLUMNS_PER_S = 50
"""Wave columns per second and channel (minimum and maximum of each), computed by the capture thread."""
RECORD_WAVE_REFRESH_HZ = 30
"""How often the window collects the new columns and repaints the waves and the meters."""
RECORD_CLIP_HOLD_S = 2.0
"""The clipping mark (0 dBFS) of a level meter stays lit this long."""
RECORD_DISCARD_CONFIRM_S = 10.0
"""[Descarta] asks for confirmation when the recording is longer than this."""
RECORD_NORMALIZE_ENABLED = True
"""On saving, a quiet recording is raised to RECORD_NORMALIZE_PEAK_DBFS (user's decision of 26/10/2026)."""
RECORD_NORMALIZE_PEAK_DBFS = -1.0
"""Peak of the saved recording after normalising; only ever raised, never lowered (no clipping)."""
RECORD_BLOCK_S = 0.05
"""Audio asked of the sound system at a time by the capture thread (the waves advance in these steps)."""
RECORD_DEVICE_POLL_S = 1.0
"""How often (seconds of audio) the capture thread checks the default output and the free space:
WASAPI does not report a change of output while recording (block C08)."""
RECORD_OPEN_TIMEOUT_S = 10.0
"""start() gives up (RecorderDeviceError) if the sound system takes longer to open the source."""
