"""B13 · The preview sustains 30 frames per second at 960x540 in real time.

The playback loop runs on its own thread with the internal clock (real time), the real
compositor and the B6 synthetic projects (every proportion, motion and fit); every frame is
also turned into a QImage, as the Player does. The report (frames per second in every second,
time to draw, distance to the clock) goes to tests/_artefactes/preview/rendiment.txt.
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from passimaker.model.types import OutputFormat, Project
from passimaker.preview import Delivery, PlaybackLoop, PlayState, Scene, to_qimage
from passimaker.timeline import time_to_frame
from tests.visual.helpers import compositor_for, synthetic_images, synthetic_projects

ARTEFACTS = Path(__file__).resolve().parents[1] / "_artefactes" / "preview"
PLAY_S = 20.0
MIN_MEAN_FPS = 29.0
MIN_SECOND_FPS = 27


def play(project: Project) -> tuple[str, bool]:
    """Plays the project in real time for PLAY_S seconds: the report line, and whether it passed."""
    size = (960, 540) if project.output_format is OutputFormat.HORIZONTAL else (540, 960)
    compositor, timeline = compositor_for(project, synthetic_images(project, max_long_side=8000))
    # Canvases of the first photos are prepared, as when the program shows the first frame.
    compositor.frame_at(0.0, *size)
    deliveries: list[tuple[Delivery, float]] = []
    start = time.perf_counter()

    def deliver(delivery: Delivery) -> None:
        to_qimage(delivery.image)
        deliveries.append((delivery, time.perf_counter() - start))

    def notify(state: PlayState) -> None:
        pass

    loop = PlaybackLoop(Scene(compositor, timeline, None), None, deliver, notify, size=size)
    loop.play()
    thread = threading.Thread(target=loop.run)
    start = time.perf_counter()
    thread.start()
    time.sleep(min(PLAY_S, timeline.total_duration_s - 0.5))
    loop.close()
    thread.join()

    played = [(d, at) for d, at in deliveries if d.clock_s is not None]
    per_second = Counter(int(at) for _, at in played)
    seconds = [per_second.get(s, 0) for s in range(1, int(max(at for _, at in played)))]
    lags = [abs(d.clock_s - d.t) * timeline.fps for d, _ in played if d.clock_s is not None]
    frames = [time_to_frame(d.t, timeline.fps) for d, _ in played]
    skipped = frames[-1] - frames[0] + 1 - len(frames)
    mean_fps = statistics.mean(seconds)
    line = (
        f"{size[0]}x{size[1]}, {len(played)} imatges en {played[-1][1]:.1f} s, "
        f"{mean_fps:.1f} imatges/s de mitjana (mín. {min(seconds)} en un segon), {skipped} saltades, "
        f"distància al rellotge {statistics.mean(lags):.2f} imatges de mitjana "
        f"i {max(lags):.2f} com a màxim"
    )
    return line, mean_fps >= MIN_MEAN_FPS and min(seconds) >= MIN_SECOND_FPS


@pytest.mark.perf
def test_thirty_frames_per_second_at_960x540() -> None:
    lines: list[str] = []
    failures: list[str] = []
    for name, project in synthetic_projects().items():
        line, passed = play(project)
        lines.append(f"{name}: {line}")
        if not passed:
            failures.append(name)
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    with (ARTEFACTS / "rendiment.txt").open("a", encoding="utf-8") as report:
        report.write(time.strftime("%Y-%m-%d %H:%M") + "\n" + "\n".join(lines) + "\n\n")
    print("\n".join(lines))
    assert failures == [], "\n".join(lines)
