"""Fixed timeline: equal durations, simple crossfades. Stands in for B2 until it is integrated.

This is deliberately simple and is NOT the specification: it ignores per-photo durations,
the crossfade clamping rules and the audio plan.
"""

from __future__ import annotations

from collections.abc import Sequence

from passi.timeline import AudioPlan, Interval, PhotoSlot, Timeline, VisibleLayer, Visibles


def fixed_timeline(
    photo_ids: Sequence[str],
    duration_s: float = 5.0,
    crossfade_s: float = 1.0,
    fade_s: float = 1.0,
    fps: int = 30,
) -> Timeline:
    total = duration_s * len(photo_ids)
    half = crossfade_s / 2
    slots: list[PhotoSlot] = []
    for i, pid in enumerate(photo_ids):
        start, end = i * duration_s, (i + 1) * duration_s
        first, last = i == 0, i == len(photo_ids) - 1
        slots.append(
            PhotoSlot(
                photo_id=pid,
                index=i,
                slot_start=start,
                slot_end=end,
                visible_start=start if first else start - half,
                visible_end=end if last else end + half,
                fade_in=None if first else Interval(start - half, start + half),
                fade_out=None if last else Interval(end - half, end + half),
            )
        )
    return Timeline(
        fps=fps,
        total_duration_s=total,
        total_frames=round(total * fps),
        slots=tuple(slots),
        fade_from_black=Interval(0.0, fade_s) if photo_ids else None,
        fade_to_black=Interval(total - fade_s, total) if photo_ids else None,
        audio_plan=AudioPlan(segments=(), final_fade=None),
        music_duration_s=0.0,
    )


def fixed_query(timeline: Timeline, t: float) -> Visibles:
    layers: list[VisibleLayer] = []
    for slot in timeline.slots:
        if not slot.visible_start <= t < slot.visible_end:
            continue
        opacity = 1.0
        if slot.fade_in is not None and t < slot.fade_in.end:
            opacity = (t - slot.fade_in.start) / (slot.fade_in.end - slot.fade_in.start)
        if slot.fade_out is not None and t > slot.fade_out.start:
            opacity = (slot.fade_out.end - t) / (slot.fade_out.end - slot.fade_out.start)
        progress = (t - slot.visible_start) / (slot.visible_end - slot.visible_start)
        layers.append(VisibleLayer(slot.photo_id, opacity, progress))
    black = 0.0
    fin, fout = timeline.fade_from_black, timeline.fade_to_black
    if fin is not None and t < fin.end:
        black = 1.0 - (t - fin.start) / (fin.end - fin.start)
    if fout is not None and t > fout.start:
        black = (t - fout.start) / (fout.end - fout.start)
    return Visibles(tuple(layers), min(1.0, max(0.0, black)))
