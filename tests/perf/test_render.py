"""B6 · Compositor speed: mean time per frame over a whole show (canvas preparation included).

Limits from the plan: <= 35 ms per frame at 1080p and <= 15 ms at 960x540. The images come
from memory, so only the compositor is measured (decoding is B4's and is prefetched).
Results are written to tests/_artefactes/render/rendiment.txt.
"""

from __future__ import annotations

import time

import pytest

from passimaker.model.types import OutputFormat
from tests.visual.helpers import ARTEFACTS, compositor_for, frame_times, synthetic_images, synthetic_projects

LIMITS_MS = {(1920, 1080): 35.0, (960, 540): 15.0}


@pytest.mark.perf
@pytest.mark.parametrize("size", list(LIMITS_MS))
def test_mean_time_per_frame(size: tuple[int, int]) -> None:
    lines: list[str] = []
    means: list[float] = []
    for name, project in synthetic_projects().items():
        width, height = size if project.output_format is OutputFormat.HORIZONTAL else size[::-1]
        compositor, timeline = compositor_for(project, synthetic_images(project, max_long_side=8000))
        times = frame_times(timeline)
        start = time.perf_counter()
        for t in times:
            compositor.frame_at(t, width, height)
        mean_ms = (time.perf_counter() - start) / len(times) * 1000
        means.append(mean_ms)
        lines.append(f"{name}: {width}x{height}, {len(times)} imatges, {mean_ms:.1f} ms per imatge")
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    with (ARTEFACTS / "rendiment.txt").open("a", encoding="utf-8") as report:
        report.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    assert max(means) <= LIMITS_MS[size]
