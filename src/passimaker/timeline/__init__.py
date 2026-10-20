"""M5 · Timeline: photo slots, fades, black fades and audio plan (block B2).

Public API: compute_timeline, query, fit_to_music, time_to_frame and frame_to_time, with the
data types of docs/CONTRACTES.md §5. Pure functions over lists of numbers: no images, no audio.
"""

from passimaker.timeline.build import compute_timeline, query
from passimaker.timeline.fit import fit_to_music
from passimaker.timeline.frames import frame_to_time, time_to_frame
from passimaker.timeline.types import (
    DEFAULT_DURATION_LIMITS,
    AudioPlan,
    AudioSegment,
    DurationLimits,
    FitResult,
    Interval,
    PhotoSlot,
    Timeline,
    VisibleLayer,
    Visibles,
)

__all__ = [
    "DEFAULT_DURATION_LIMITS",
    "AudioPlan",
    "AudioSegment",
    "DurationLimits",
    "FitResult",
    "Interval",
    "PhotoSlot",
    "Timeline",
    "VisibleLayer",
    "Visibles",
    "compute_timeline",
    "fit_to_music",
    "frame_to_time",
    "query",
    "time_to_frame",
]
