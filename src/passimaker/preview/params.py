"""Internal parameters of the preview player (one single place, like passimaker.render.params)."""

from __future__ import annotations

PREVIEW_MAX_SIZE = (960, 540)
"""Largest frame drawn by the preview (540x960 in vertical): §1.8."""

MAX_WAIT_S = 0.010
"""While playing, the render thread never sleeps longer than this before reading the clock again."""

COST_INITIAL_S = 1 / 30
"""Estimate of the time to draw a frame before the first one has been measured."""
COST_SMOOTHING = 0.3
"""Weight of the last measured drawing time in the running estimate (exponential average)."""
COST_MAX_S = 0.5
"""The estimate is capped here, so one very slow frame (a photo decoded on demand) cannot make the
player aim far ahead of the sound."""

AUDIO_BLOCK_FRAMES = 1024
"""Frames per audio callback (21 ms at 48 kHz)."""
AUDIO_BUFFER_BLOCKS = 8
"""Blocks mixed ahead of the sound card (~170 ms): the sound never stops if a frame is slow."""
AUDIO_LATENCY = "high"
"""PortAudio latency setting: the stable choice on every Windows driver; the clock compensates it."""

THREAD_JOIN_TIMEOUT_S = 5.0
"""How long close() waits for the render thread (it only waits for the frame being drawn)."""
