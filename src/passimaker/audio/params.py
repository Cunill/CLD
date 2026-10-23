"""Internal parameters of the audio engine (one single place, like passimaker.motion.params).

User-facing defaults and ranges (fade lengths, volumes, loudness target, limiter ceiling) live in
passimaker.model.defaults; these are the engine's own constants.
"""

from __future__ import annotations

from passimaker.model import defaults

SAMPLE_RATE = 48000
CHANNELS = 2

FADE_FLOOR_DB = -60.0
"""Fade curve: the gain moves linearly in dB from this level to 0 dB (and is anchored to 0 at the
very start), which the ear hears as an even change of loudness (§1.7, "corba logarítmica")."""

ANTI_CLICK_MAX_FRAMES = round(defaults.CUT_MICRO_FADE_S * SAMPLE_RATE)
"""Fades up to this long (the 10 ms fade of every cut) use a raised cosine instead of the log curve."""

LIMITER_LOOKAHEAD_S = 0.005
"""The limiter starts lowering the gain this long before a peak (and releases over the same time)."""
LIMITER_HOLD_S = 0.050
"""After a peak the reduced gain is held this long before it is released (avoids distortion)."""

MAX_NORMALIZE_GAIN_DB = 20.0
"""Normalisation never raises a very quiet song by more than this (it would only raise its noise)."""
SILENCE_LUFS = -70.0
"""A song measured at or below this level (the EBU R128 absolute gate) is silence: gain 0 dB."""

LIMITER_CEILING = 10.0 ** (defaults.LIMITER_CEILING_DBFS / 20.0) - 1.0 / 32767
"""Linear ceiling: −1 dBFS less one 16-bit step, so that rounding to 16 bits never goes above it."""

RENDER_BLOCK_FRAMES = 1 << 18
"""render_wav mixes and writes this many frames at a time (~5.5 s, ~2 MB): constant memory."""

CACHE_VERSION = 1
"""Part of every cache key: increase it when the decoded format changes."""

CACHE_LIMIT_BYTES = 2 * 1024**3
"""The decoded songs kept on disk (23 MB a minute) stay under this size, least recently used first
(B15; the same limit as the thumbnails of B5). The songs in use by the program are never dropped."""
