"""B4: CachedImageSource memory budget, reuse, prefetch and thread safety."""

from __future__ import annotations

import os
import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from passimaker.images import CachedImageSource, ImageDecodeError, ImageSource
from passimaker.images import source as source_module
from passimaker.model.types import Rotation
from tests.unit.images.helpers import photo_for
from tests.unit.images.samples import pattern, write_jpeg


@pytest.fixture(scope="module")
def many_photos(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """200 different small JPEGs (300×200)."""
    folder = tmp_path_factory.mktemp("many")
    return [write_jpeg(folder / f"p{i:03}.jpg", pattern(f"p{i}", 300, 200)) for i in range(200)]


def test_it_implements_the_protocol() -> None:
    source: ImageSource = CachedImageSource()
    assert callable(source.get_image) and callable(source.prefetch)


def test_a_second_request_is_served_from_memory(many_photos: list[Path]) -> None:
    source = CachedImageSource()
    photo = photo_for(many_photos[0])
    first = source.get_image(photo, 200)
    assert source.get_image(photo, 200) is first
    assert source.get_image(photo, 160) is first  # within [target, 2 × target]
    assert source.decode_count == 1


def test_returned_images_are_read_only(many_photos: list[Path]) -> None:
    image = CachedImageSource().get_image(photo_for(many_photos[0]), 200)
    with pytest.raises(ValueError, match="read-only"):
        image[0, 0, 0] = 1


def test_a_much_smaller_request_reduces_the_cached_image(fixture_files: dict[str, Path]) -> None:
    source = CachedImageSource()
    photo = photo_for(fixture_files["ratio_4x3.jpg"])
    source.get_image(photo, 1600)
    small = source.get_image(photo, 200)
    assert source.decode_count == 1
    assert max(small.shape[:2]) == 200


def test_a_larger_request_decodes_again_unless_the_original_is_cached(fixture_files: dict[str, Path]) -> None:
    source = CachedImageSource()
    photo = photo_for(fixture_files["ratio_4x3.jpg"])
    source.get_image(photo, 400)
    full = source.get_image(photo, 1600)
    assert source.decode_count == 2 and full.shape == (1200, 1600, 3)
    assert source.get_image(photo, 5000) is full  # the original is the largest there is
    assert source.decode_count == 2


def test_rotation_is_part_of_the_key(many_photos: list[Path]) -> None:
    source = CachedImageSource()
    plain = source.get_image(photo_for(many_photos[0]), 300)
    turned = source.get_image(photo_for(many_photos[0], Rotation.R90), 300)
    assert plain.shape == (200, 300, 3) and turned.shape == (300, 200, 3)
    assert source.decode_count == 2


def test_a_modified_file_is_decoded_again(tmp_path: Path) -> None:
    path = write_jpeg(tmp_path / "edit.jpg", np.full((200, 300, 3), (180, 120, 60), dtype=np.uint8))
    source = CachedImageSource()
    before = source.get_image(photo_for(path), 300)
    write_jpeg(path, np.full((200, 300, 3), (60, 120, 180), dtype=np.uint8))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    after = source.get_image(photo_for(path), 300)
    assert source.decode_count == 2
    assert before[100, 150, 0] > 150 and after[100, 150, 0] < 90


def test_the_budget_is_never_exceeded_with_200_photos(many_photos: list[Path]) -> None:
    one = 300 * 200 * 3
    budget = 25 * one + one // 2
    source = CachedImageSource(memory_budget_bytes=budget)
    for path in many_photos:
        source.get_image(photo_for(path), 300)
        assert source.cached_bytes <= budget
    assert source.cached_bytes == 25 * one
    decoded = source.decode_count
    source.get_image(photo_for(many_photos[-1]), 300)  # most recent: still there
    assert source.decode_count == decoded
    source.get_image(photo_for(many_photos[0]), 300)  # oldest: dropped
    assert source.decode_count == decoded + 1


def test_least_recently_used_goes_first(many_photos: list[Path]) -> None:
    one = 300 * 200 * 3
    source = CachedImageSource(memory_budget_bytes=3 * one)
    a, b, c, d = (photo_for(p) for p in many_photos[:4])
    for photo in (a, b, c):
        source.get_image(photo, 300)
    source.get_image(a, 300)  # a becomes the most recent
    source.get_image(d, 300)  # drops b
    count = source.decode_count
    source.get_image(a, 300)
    source.get_image(c, 300)
    assert source.decode_count == count
    source.get_image(b, 300)
    assert source.decode_count == count + 1


def test_an_image_larger_than_the_budget_is_returned_but_not_kept(many_photos: list[Path]) -> None:
    source = CachedImageSource(memory_budget_bytes=1000)
    image = source.get_image(photo_for(many_photos[0]), 300)
    assert image.shape == (200, 300, 3)
    assert source.cached_bytes == 0


def _slow_decode(monkeypatch: pytest.MonkeyPatch, delay: float = 0.05) -> tuple[list[int], Callable[[], int]]:
    """Wraps the decoder to measure how many decodings run at the same time."""
    active = [0]
    peak = [0]
    lock = threading.Lock()
    real = source_module.decode

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            time.sleep(delay)
            return real(*args, **kwargs)
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(source_module, "decode", wrapped)
    return active, lambda: peak[0]


def _wait_for(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def test_prefetch_returns_at_once_and_decodes_in_parallel(
    monkeypatch: pytest.MonkeyPatch, many_photos: list[Path]
) -> None:
    _, peak = _slow_decode(monkeypatch, delay=0.1)
    source = CachedImageSource(workers=2)
    photos = [photo_for(p) for p in many_photos[:8]]
    start = time.perf_counter()
    source.prefetch(photos, 300)
    assert time.perf_counter() - start < 0.05
    _wait_for(lambda: source.decode_count == 8 and source.cached_bytes == 8 * 300 * 200 * 3)
    assert peak() == 2
    for photo in photos:
        source.get_image(photo, 300)
    assert source.decode_count == 8
    source.close()


def test_concurrent_requests_for_one_image_decode_it_once(
    monkeypatch: pytest.MonkeyPatch, many_photos: list[Path]
) -> None:
    _slow_decode(monkeypatch, delay=0.2)
    source = CachedImageSource()
    photo = photo_for(many_photos[0])
    results: list[np.ndarray] = []
    threads = [
        threading.Thread(target=lambda: results.append(source.get_image(photo, 300))) for _ in range(8)
    ]
    source.prefetch([photo], 300)
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert source.decode_count == 1
    assert len(results) == 8 and all(r is results[0] for r in results)


def test_many_threads_with_a_small_budget(many_photos: list[Path]) -> None:
    """Random requests from 8 threads plus prefetches, with constant eviction."""
    one = 300 * 200 * 3
    budget = 10 * one
    source = CachedImageSource(memory_budget_bytes=budget, workers=3)
    pool = [photo_for(p) for p in many_photos[:30]]
    reference = {p.id: CachedImageSource().get_image(p, 300).copy() for p in pool}
    errors: list[BaseException] = []

    def worker(seed: int) -> None:
        rng = random.Random(seed)
        try:
            for _ in range(60):
                photo = rng.choice(pool)
                if rng.random() < 0.1:
                    source.prefetch(rng.sample(pool, 3), 300)
                size = rng.choice([150, 200, 300, 600])
                image = source.get_image(photo, size)
                assert max(image.shape[:2]) in ({150, 300} if size == 150 else {300})
                if size >= 300:
                    np.testing.assert_array_equal(image, reference[photo.id])
                assert source.cached_bytes <= budget
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    source.close()
    assert errors == []


def test_prefetch_errors_are_swallowed_and_reported_later(fixture_files: dict[str, Path]) -> None:
    source = CachedImageSource()
    broken = photo_for(fixture_files["corrupt.jpg"])
    source.prefetch([broken], 300)
    _wait_for(lambda: source.decode_count == 1)
    with pytest.raises(ImageDecodeError):
        source.get_image(broken, 300)
    source.close()


def test_after_close_prefetch_does_nothing_but_get_image_works(many_photos: list[Path]) -> None:
    source = CachedImageSource()
    source.get_image(photo_for(many_photos[0]), 300)
    source.close()
    assert source.cached_bytes == 0
    source.prefetch([photo_for(many_photos[1])], 300)
    time.sleep(0.05)
    assert source.decode_count == 1
    assert source.get_image(photo_for(many_photos[1]), 300).shape == (200, 300, 3)
    source.close()  # twice is fine
