"""Builders shared by the motion tests."""

from __future__ import annotations

from collections.abc import Sequence

from passi.model.types import FitMode, Intensity, MotionMode, MotionType, OutputFormat, PhotoMotion
from passi.motion import MotionRequest, base_window, draw_motions, resolve_fit

DEFAULT_VISIBLE_S = 3.0  # 2 s photo + half of a 1 s crossfade on each side


def request(
    photo_id: str,
    width: int = 4000,
    height: int = 3000,
    *,
    output_format: OutputFormat = OutputFormat.HORIZONTAL,
    fit: FitMode = FitMode.AUTO,
    duration: float = DEFAULT_VISIBLE_S,
    mode: MotionMode = MotionMode.AUTO,
    manual_type: MotionType | None = None,
    draw_count: int = 0,
    current: PhotoMotion | None = None,
) -> MotionRequest:
    return MotionRequest(
        photo_id=photo_id,
        width=width,
        height=height,
        visible_duration_s=duration,
        fit=resolve_fit(width, height, output_format, fit),
        output_format=output_format,
        mode=mode,
        manual_type=manual_type,
        draw_count=draw_count,
        current=current,
    )


def base_of(req: MotionRequest) -> tuple[float, float]:
    return base_window(req.fit.canvas_width, req.fit.canvas_height, req.output_format)


def draw_sequence(
    sizes: Sequence[tuple[int, int]],
    seed: int = 1,
    intensity: Intensity = Intensity.MEDIUM,
    output_format: OutputFormat = OutputFormat.HORIZONTAL,
) -> tuple[list[MotionRequest], list[PhotoMotion]]:
    requests = [request(f"p{i:04d}", w, h, output_format=output_format) for i, (w, h) in enumerate(sizes)]
    motions = draw_motions(requests, seed, intensity)
    return requests, [motions[r.photo_id] for r in requests]
