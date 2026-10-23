"""Internal parameters of the export (not user settings: those live in passimaker.model.defaults)."""

from __future__ import annotations

RENDER_THREADS = 2
"""Threads calling Compositor.frame_at at the same time (thread-safe, B6); ffmpeg encodes in parallel."""

FRAMES_IN_FLIGHT = 6
"""Frames requested ahead of the one being written (bounded memory: ~6 MB each at 1080p)."""

AUDIO_SHARE = 0.04
"""Fraction of the progress bar given to rendering the WAV (80 min of audio take ~8 s, B8)."""

FINISH_SHARE = 0.02
"""Fraction of the progress bar kept for closing the encoder (faststart rewrites the whole file)."""

PROGRESS_INTERVAL_S = 0.1
"""Minimum time between two progress calls (the first and the last are always sent)."""

ETA_MIN_FRAMES = 15
"""Frames written before the remaining time is estimated (the first ones include warm-up)."""

VIDEO_BYTES_PER_S = 1_000_000
"""Size estimate of the video for the free-space check (8 Mbit/s: CRF 18, 1080p, slow motion)."""

DISK_MARGIN_BYTES = 64 * 1024 * 1024
"""Free space left over after the estimate (the file system needs some to keep working)."""

CANCEL_POLL_S = 0.05
"""How often a cancelled export checks the token while waiting for a frame."""

IMAGE_MEMORY_BYTES = 384 * 1024 * 1024
"""Decoded photos kept by the export (B15). The export walks the photos in order and needs only the
ones on screen and the next PREFETCH_AHEAD; with the 768 MB of the window's image source, 1,000 photos
of 24 MP took the export to 1.6 GB (limit: 1.5 GB)."""
