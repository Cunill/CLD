"""B5: 1,000 photos, all thumbnails in less than 60 s the first time and in less than 3 s afterwards.

Runs in CI (marker `lent`, not `perf`). The times are written to tests/_artefactes/thumbs/temps.txt.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image

from passimaker.images import CachedImageSource
from passimaker.thumbs import Priority, ThumbnailService
from tests.unit.thumbs.helpers import (
    Collector,
    copies,
    exif_with_thumbnail,
    photo_for,
    pseudo_photo,
    write_jpeg,
)

ARTEFACTS = Path(__file__).resolve().parents[2] / "_artefactes" / "thumbs"
FIRST_LIMIT_S = 60.0
AGAIN_LIMIT_S = 3.0


def _photos(folder: Path) -> list[Path]:
    """1,000 files in the proportions of a real import: mostly camera JPEGs, some PNG and HEIC."""
    bases = folder / "bases"
    bases.mkdir(parents=True)
    camera = write_jpeg(
        bases / "camera.jpg", pseudo_photo(4000, 3000, 1), exif_with_thumbnail(pseudo_photo(160, 120, 2), 6)
    )
    phone = write_jpeg(bases / "mobil.jpg", pseudo_photo(3000, 2000, 3))
    png = bases / "captura.png"
    Image.fromarray(pseudo_photo(2000, 1500, 4)).save(png, compress_level=6)
    heic = bases / "iphone.heic"
    Image.fromarray(pseudo_photo(2000, 1500, 5)).save(heic, "HEIF", quality=80)
    paths: list[Path] = []
    for base, count in ((camera, 400), (phone, 500), (png, 50), (heic, 50)):
        paths += copies(base, folder / "fotos", count, base.stem)
    return paths


def _run(service: ThumbnailService, paths: list[Path]) -> tuple[float, Collector]:
    collector = Collector()
    start = time.perf_counter()
    for i, path in enumerate(paths):
        priority = Priority.VISIBLE if i < 40 else Priority.NORMAL
        service.request_thumbnail(photo_for(path, photo_id=f"p{i}"), priority, collector)
    assert collector.wait(len(paths), 2 * FIRST_LIMIT_S)
    return time.perf_counter() - start, collector


@pytest.mark.lent
def test_thousand_photos(tmp_path: Path) -> None:
    paths = _photos(tmp_path)
    cache = tmp_path / "cache"
    images = CachedImageSource(memory_budget_bytes=128 * 1024 * 1024)
    try:
        service = ThumbnailService(cache, images)
        first, results = _run(service, paths)
        service.close()
        assert all(image is not None for image in results.results.values())
        service = ThumbnailService(cache, images)
        decoded = images.decode_count
        again, results = _run(service, paths)
        service.close()
        assert images.decode_count == decoded
        assert all(image is not None for image in results.results.values())
    finally:
        images.close()
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    (ARTEFACTS / "temps.txt").write_text(
        f"1.000 miniatures, primera vegada: {first:.1f} s (límit {FIRST_LIMIT_S:.0f} s)\n"
        f"1.000 miniatures, des del disc: {again:.2f} s (límit {AGAIN_LIMIT_S:.0f} s)\n",
        encoding="utf-8",
    )
    print(f"\nminiatures: primera vegada {first:.1f} s, des del disc {again:.2f} s")
    assert first < FIRST_LIMIT_S
    assert again < AGAIN_LIMIT_S
