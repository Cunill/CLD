"""M10 · Real-time preview player (block B13). Qt is allowed here.

Public API (docs/CONTRACTES.md §10): Player, Clock, AudioOutput and PREVIEW_MAX_SIZE; plus the
pieces the interface and the tests build it with: the internal clock, the real sound output and
the scene helpers (photo_start, photo_index_at, same_place).

How it works: passimaker.preview.loop (the playback loop, no Qt), passimaker.preview.scheduler
(which frame to draw next), passimaker.preview.sound (sound card and its clock) and
passimaker.preview.player (the thread and the Qt signals).
"""

from __future__ import annotations

from passimaker.preview.clock import ClockFactory, MonotonicClock
from passimaker.preview.loop import (
    Delivery,
    PlaybackLoop,
    PlayState,
    Scene,
    photo_index_at,
    photo_start,
    same_place,
)
from passimaker.preview.params import PREVIEW_MAX_SIZE
from passimaker.preview.player import Player, to_qimage
from passimaker.preview.scheduler import FrameScheduler
from passimaker.preview.sound import SoundDeviceOutput, StreamClock
from passimaker.preview.types import AudioOutput, Clock, FrameSource

__all__ = [
    "PREVIEW_MAX_SIZE",
    "AudioOutput",
    "Clock",
    "ClockFactory",
    "Delivery",
    "FrameScheduler",
    "FrameSource",
    "MonotonicClock",
    "PlayState",
    "PlaybackLoop",
    "Player",
    "Scene",
    "SoundDeviceOutput",
    "StreamClock",
    "photo_index_at",
    "photo_start",
    "same_place",
    "to_qimage",
]
