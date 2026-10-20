"""B4 performance targets (marker perf: run locally on the reference PC and at milestones)."""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from passimaker.images import CachedImageSource
from tests.unit.images.helpers import photo_for
from tests.unit.images.samples import pattern

pytestmark = pytest.mark.perf


@pytest.fixture(scope="module")
def jpeg_50mp(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """8700×5800 (50.5 MP) with sensor-like noise, so that it costs what a camera JPEG costs."""
    small = Image.fromarray(pattern("50mp", 2175, 1450)).resize((8700, 5800), Image.Resampling.BILINEAR)
    pixels = np.asarray(small, dtype=np.int16)
    noise = np.random.default_rng(50).normal(0, 6, pixels.shape[:2])[..., None].astype(np.int16)
    path = tmp_path_factory.mktemp("perf") / "50mp.jpg"
    Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8)).save(path, "JPEG", quality=92)
    return path


def test_50_mp_jpeg_reduced_to_2000_px_in_less_than_400_ms(jpeg_50mp: Path) -> None:
    times: list[float] = []
    for _ in range(5):
        source = CachedImageSource()
        start = time.perf_counter()
        image = source.get_image(photo_for(jpeg_50mp), 2000)
        times.append(time.perf_counter() - start)
        assert 2000 <= max(image.shape[:2]) <= 4000
    median = statistics.median(times)
    print(f"\n50 MP -> 2000 px: median {median * 1000:.0f} ms, max {max(times) * 1000:.0f} ms")
    assert median < 0.4


def test_prefetch_uses_both_workers(jpeg_50mp: Path, tmp_path: Path) -> None:
    copies = []
    for i in range(4):
        copy = tmp_path / f"copy{i}.jpg"
        copy.write_bytes(jpeg_50mp.read_bytes())
        copies.append(photo_for(copy))
    serial = CachedImageSource(workers=1)
    start = time.perf_counter()
    for photo in copies:
        serial.get_image(photo, 2000)
    one_by_one = time.perf_counter() - start

    parallel = CachedImageSource(workers=2)
    start = time.perf_counter()
    parallel.prefetch(copies, 2000)
    while parallel.decode_count < 4 or len({id(parallel.get_image(p, 2000)) for p in copies}) < 4:
        time.sleep(0.005)
    both = time.perf_counter() - start
    print(f"\n4 × 50 MP: serial {one_by_one:.2f} s, 2 workers {both:.2f} s")
    assert both < 0.8 * one_by_one
