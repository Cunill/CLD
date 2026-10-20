"""B3 · No edges, ever: 10,000 random cases (proportions, durations, intensities, types, formats)."""

from __future__ import annotations

import numpy as np

from passimaker.model.types import FitMode, Intensity, MotionMode, MotionType, OutputFormat
from passimaker.motion import draw_motions, is_inside, window_at
from tests.unit.motion.helpers import base_of, request

CASES = 10_000
CHECKPOINTS = np.linspace(0.0, 1.0, 52)  # start, end and 50 intermediate instants


def test_ten_thousand_random_motions_never_leave_the_canvas() -> None:
    rng = np.random.default_rng(20261020)
    types = list(MotionType)
    intensities = list(Intensity)
    formats = list(OutputFormat)
    fits = list(FitMode)
    violations: list[str] = []
    for case in range(CASES):
        width = int(rng.integers(64, 12_000))
        height = int(np.clip(width / rng.uniform(0.2, 5.0), 64, 12_000))
        manual = bool(rng.random() < 0.5)
        req = request(
            f"c{case}",
            width,
            height,
            output_format=formats[int(rng.integers(len(formats)))],
            fit=fits[int(rng.integers(len(fits)))],
            duration=float(rng.uniform(1.0, 31.0)),
            mode=MotionMode.MANUAL if manual else MotionMode.AUTO,
            manual_type=types[int(rng.integers(len(types)))] if manual else None,
            draw_count=int(rng.integers(0, 5)),
        )
        intensity = intensities[int(rng.integers(len(intensities)))]
        motion = draw_motions([req], int(rng.integers(0, 2**31)), intensity)[req.photo_id]
        base = base_of(req)
        for p in CHECKPOINTS:
            if not is_inside(window_at(motion, float(p)), base):
                violations.append(f"{req} {motion} p={p}")
                break
    assert violations == []


def test_sequences_in_both_formats_never_leave_the_canvas() -> None:
    rng = np.random.default_rng(7)
    for output_format in OutputFormat:
        sizes = [(int(rng.integers(300, 9000)), int(rng.integers(300, 9000))) for _ in range(500)]
        requests = [request(f"s{i}", w, h, output_format=output_format) for i, (w, h) in enumerate(sizes)]
        motions = draw_motions(requests, 3, Intensity.STRONG)
        for req in requests:
            base = base_of(req)
            assert all(is_inside(window_at(motions[req.photo_id], float(p)), base) for p in CHECKPOINTS)
