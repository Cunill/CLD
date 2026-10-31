"""Photo slots, crossfades and black fades, and what is on screen at time t (§1.3, §1.4)."""

from __future__ import annotations

import bisect
import itertools
from collections.abc import Sequence

from passimaker.model import defaults
from passimaker.model.types import BlackSlide, Project
from passimaker.timeline.audio_plan import build_audio_plan, music_duration
from passimaker.timeline.types import Interval, PhotoSlot, Timeline, VisibleLayer, Visibles


def compute_timeline(project: Project, fps: int = defaults.FPS) -> Timeline:
    """Lays out the slides (photos and black slides, M08) one after another; each one occupies exactly
    its duration.

    Values are expected to be within the ranges of passimaker.model.defaults (the controller
    clamps them); negative values are treated as 0 so the result is always consistent.
    """
    durations = [max(0.0, project.photo_duration(s)) for s in project.slides]
    bounds = [0.0, *itertools.accumulate(durations)]
    total = bounds[-1]
    crossfades = _crossfades(durations, max(0.0, project.crossfade_s))
    slots = tuple(
        _slot(
            slide.id,
            isinstance(slide, BlackSlide),
            i,
            bounds[i],
            bounds[i + 1],
            crossfades[i - 1] if i > 0 else 0.0,
            crossfades[i] if i < len(crossfades) else 0.0,
        )
        for i, slide in enumerate(project.slides)
    )
    fade_from_black, fade_to_black = _black_fades(
        total, max(0.0, project.fade_from_black_s), max(0.0, project.fade_to_black_s)
    )
    return Timeline(
        fps=fps,
        total_duration_s=total,
        total_frames=round(total * fps),
        slots=slots,
        fade_from_black=fade_from_black,
        fade_to_black=fade_to_black,
        audio_plan=build_audio_plan(
            project.music.songs, total, fps, project.music.silence_start_s, project.music.silence_end_s
        ),
        music_duration_s=music_duration(project.music.songs),
    )


def _crossfades(durations: Sequence[float], crossfade: float) -> list[float]:
    """Safety rule: a crossfade never lasts more than half of the shorter of its two photos."""
    return [min(crossfade, a / 2, b / 2) for a, b in itertools.pairwise(durations)]


def _slot(
    photo_id: str, black: bool, index: int, start: float, end: float, before: float, after: float
) -> PhotoSlot:
    """`before` and `after` are the crossfades centred on the start and on the end of the slot."""
    fade_in = _interval(start - before / 2, start + before / 2)
    fade_out = _interval(end - after / 2, end + after / 2)
    return PhotoSlot(
        photo_id=photo_id,
        index=index,
        slot_start=start,
        slot_end=end,
        visible_start=fade_in.start if fade_in is not None else start,
        visible_end=fade_out.end if fade_out is not None else end,
        fade_in=fade_in,
        fade_out=fade_out,
        black=black,
    )


def _black_fades(total: float, fade_in: float, fade_out: float) -> tuple[Interval | None, Interval | None]:
    """Black fades that do not fit in the show are shortened proportionally."""
    if fade_in + fade_out > total:
        scale = total / (fade_in + fade_out) if total > 0 else 0.0
        fade_in, fade_out = fade_in * scale, fade_out * scale
    return _interval(0.0, min(total, fade_in)), _interval(max(0.0, total - fade_out), total)


def _interval(start: float, end: float) -> Interval | None:
    """None for fades too short to have any length once rounded to floats."""
    return Interval(start, end) if end > start else None


def query(timeline: Timeline, t: float) -> Visibles:
    """What is on screen at time t: up to two photos (outgoing below, incoming on top).

    Outside the black fades the opacities add up to 1. Times outside [0, total] are black.
    """
    slots = timeline.slots
    total = timeline.total_duration_s
    if not slots or not 0.0 <= t <= total:
        return Visibles((), 1.0)
    # The slot that contains t (the last one for t == total); its neighbours may be fading.
    current = min(bisect.bisect_right(slots, t, key=lambda s: s.slot_start) - 1, len(slots) - 1)
    layers: list[VisibleLayer] = []
    for slot in slots[max(0, current - 1) : current + 2]:
        layer = _layer(slot, t, is_last=slot.index == len(slots) - 1)
        if layer is not None:
            layers.append(layer)
    return Visibles(tuple(layers), _black_level(timeline, t))


def _layer(slot: PhotoSlot, t: float, is_last: bool) -> VisibleLayer | None:
    inside = slot.visible_start <= t < slot.visible_end or (is_last and t == slot.visible_end)
    if not inside or slot.visible_end <= slot.visible_start:
        return None
    opacity = 1.0
    if slot.fade_in is not None and t < slot.fade_in.end:
        opacity = _ramp(slot.fade_in, t)
    elif slot.fade_out is not None and t > slot.fade_out.start:
        opacity = 1.0 - _ramp(slot.fade_out, t)
    if opacity <= 0.0:
        return None
    progress = (t - slot.visible_start) / (slot.visible_end - slot.visible_start)
    return VisibleLayer(slot.photo_id, opacity, min(1.0, max(0.0, progress)), slot.black)


def _ramp(interval: Interval, t: float) -> float:
    """0 at the start of the interval, 1 at its end (the incoming photo's opacity)."""
    if interval.end <= interval.start:
        return 1.0 if t >= interval.end else 0.0
    return min(1.0, max(0.0, (t - interval.start) / (interval.end - interval.start)))


def _black_level(timeline: Timeline, t: float) -> float:
    level = 0.0
    if timeline.fade_from_black is not None and t < timeline.fade_from_black.end:
        level = 1.0 - _ramp(timeline.fade_from_black, t)
    if timeline.fade_to_black is not None and t > timeline.fade_to_black.start:
        level = max(level, _ramp(timeline.fade_to_black, t))
    return level
