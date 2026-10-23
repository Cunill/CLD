"""B13 · Ten minutes of simulated playback of a 1.000-photo project: the memory stays stable.

The real compositor draws at 960x540 from images made on demand (a new array for every request,
as a decoder would); the clock is simulated and every frame costs 0.1 s of it, so ten minutes of
show (300 photos) take well under a minute. The memory used by the process is sampled every
simulated 10 s; after the first three minutes (the compositor's canvas cache is full by then)
it must stay within ±50 MB. The curve is written to tests/_artefactes/preview/memoria.txt.
"""

from __future__ import annotations

import ctypes
import gc
import sys
import zlib
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest

from passimaker.common import RGBImage
from passimaker.model import Photo
from passimaker.preview import Delivery, PlaybackLoop, PlayState, Scene, to_qimage
from passimaker.render import Compositor
from passimaker.timeline import compute_timeline
from tests.fakes.audio import ToneAudioSource
from tests.fakes.clock import SimulatedClock
from tests.fixtures.generate import synthetic_rgb
from tests.ui.helpers import controller_with
from tests.unit.preview.fakes import FakeAudioOutput, SlowFrames

ARTEFACTS = Path(__file__).resolve().parents[2] / "_artefactes" / "preview"
SHOW_S = 600.0
WARM_UP_S = 180.0
SAMPLE_EVERY_S = 10.0
LIMIT_BYTES = 50 * 1024 * 1024


def resident_bytes() -> int:
    """Memory of the process in RAM (Linux: /proc; Windows: GetProcessMemoryInfo)."""
    if sys.platform == "win32":

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        windll = ctypes.windll  # type: ignore[attr-defined]
        process = windll.kernel32.GetCurrentProcess()
        assert windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
        return int(counters.WorkingSetSize)
    with Path("/proc/self/statm").open(encoding="ascii") as statm:
        return int(statm.read().split()[1]) * 4096


class TextureSource:
    """ImageSource: one texture per proportion, resized into a new array for every request."""

    def __init__(self) -> None:
        self._bases: dict[tuple[int, int], RGBImage] = {}

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        key = (photo.width, photo.height)
        base = self._bases.get(key)
        if base is None:
            scale = 1600 / max(key)
            size = (round(photo.width * scale), round(photo.height * scale))
            base = self._bases[key] = synthetic_rgb(*size, zlib.crc32(repr(key).encode()))
        long_side = min(max(photo.width, photo.height), max(min_long_side, 16))
        scale = long_side / max(base.shape[:2])
        size = (max(1, round(base.shape[1] * scale)), max(1, round(base.shape[0] * scale)))
        image = np.asarray(cv2.resize(base, size, interpolation=cv2.INTER_LINEAR), dtype=np.uint8)
        image.setflags(write=False)
        return image

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        pass


@pytest.mark.lent
def test_ten_minutes_of_playback_keep_the_memory_stable() -> None:
    project = controller_with(1000).project
    timeline = compute_timeline(project)
    assert timeline.total_duration_s >= SHOW_S
    clock = SimulatedClock()
    output = FakeAudioOutput(clock)
    frames = SlowFrames(clock, (0.1,), Compositor(project, timeline, TextureSource()))
    shown: list[object] = [None]

    def deliver(delivery: Delivery) -> None:
        shown[0] = to_qimage(delivery.image)  # as the Player does; only the last one is kept

    def notify(state: PlayState) -> None:
        pass

    def wait(timeout_s: float | None) -> None:
        if timeout_s is not None:
            clock.advance(timeout_s)

    loop = PlaybackLoop(
        Scene(frames, timeline, ToneAudioSource(timeline.total_duration_s)),
        output,
        deliver,
        notify,
        size=(960, 540),
    )
    loop.play()
    samples: list[tuple[float, int]] = []
    next_sample = 0.0
    while clock.now() < SHOW_S:
        loop.step(wait)
        if clock.now() >= next_sample:
            gc.collect()
            samples.append((clock.now(), resident_bytes()))
            next_sample += SAMPLE_EVERY_S
    loop.close()

    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    lines = [f"{t:6.0f} s  {rss / 2**20:8.1f} MB" for t, rss in samples]
    stable = [rss for t, rss in samples if t >= WARM_UP_S]
    summary = (
        f"Previsualització simulada de {SHOW_S:.0f} s, {len(project.photos)} fotos, "
        f"{len(frames.times)} imatges a 960x540. "
        f"Després de {WARM_UP_S:.0f} s: mín. {min(stable) / 2**20:.1f} MB, "
        f"màx. {max(stable) / 2**20:.1f} MB, variació {(max(stable) - min(stable)) / 2**20:.1f} MB."
    )
    (ARTEFACTS / "memoria.txt").write_text(summary + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(summary)
    # The photos really went by: about 300 of them (2 s each) in ten minutes.
    assert len({t // 2 for t in frames.times}) >= 250
    assert output.starts == [0.0]
    baseline = stable[0]
    assert all(abs(rss - baseline) <= LIMIT_BYTES for rss in stable), summary
