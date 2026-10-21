"""B5: disk cache identity (path, modification time, size), size limit and robustness."""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

from passimaker.model.types import Rotation
from passimaker.thumbs import Priority, ThumbnailService
from passimaker.thumbs.disk import CacheKey, DiskCache, FileState, Kind
from tests.unit.thumbs.conftest import ServiceFactory
from tests.unit.thumbs.helpers import Collector, RecordingSource, copies, photo_for, pseudo_photo, write_jpeg


def _cache_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.name.endswith((".thumb.jpg", ".inter.jpg")))


def _request_all(service: ThumbnailService, paths: list[Path]) -> Collector:
    collector = Collector()
    for path in paths:
        service.request_thumbnail(photo_for(path), Priority.NORMAL, collector)
    assert collector.wait(len(paths), 30)
    return collector


def test_second_service_reads_thumbnails_from_disk(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    paths = copies(write_jpeg(tmp_path / "base.jpg", pseudo_photo(1200, 800)), tmp_path / "fotos", 5)
    first = _request_all(make_service(source), paths)
    assert len(source.calls) == 5
    assert len(_cache_files(tmp_path / "cache")) == 5
    second = _request_all(make_service(source), paths)
    assert len(source.calls) == 5
    for name, image in first.results.items():
        again = second.results[name]
        assert image is not None and again is not None
        assert np.abs(image.astype(int) - again.astype(int)).mean() < 1.5


def test_changed_file_is_regenerated_and_replaces_the_old_entry(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "foto.jpg", pseudo_photo(1200, 800))
    _request_all(make_service(source), [path])
    old_files = _cache_files(tmp_path / "cache")
    # Same size, new contents and modification time (an edit in another program).
    image = np.zeros((800, 1200, 3), dtype=np.uint8)
    image[:] = (200, 40, 40)
    write_jpeg(path, image)
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
    result = _request_all(make_service(source), [path]).results["foto.jpg"]
    assert len(source.calls) == 2
    assert result is not None and np.abs(result.astype(int) - (200, 40, 40)).max() < 12
    new_files = _cache_files(tmp_path / "cache")
    assert len(new_files) == 1 and new_files != old_files


def test_same_contents_with_another_size_or_time_is_a_different_key(tmp_path: Path) -> None:
    path = write_jpeg(tmp_path / "foto.jpg", pseudo_photo(100, 80))
    state = FileState.of(path)
    key = CacheKey(state, Rotation.R0, Kind.THUMBNAIL)
    names = {
        key.filename,
        CacheKey(FileState(state.path, state.mtime_ns + 1, state.size), Rotation.R0, Kind.THUMBNAIL).filename,
        CacheKey(FileState(state.path, state.mtime_ns, state.size + 1), Rotation.R0, Kind.THUMBNAIL).filename,
        CacheKey(state, Rotation.R90, Kind.THUMBNAIL).filename,
        CacheKey(state, Rotation.R0, Kind.INTERMEDIATE).filename,
        CacheKey(
            FileState(state.path + "x", state.mtime_ns, state.size), Rotation.R0, Kind.THUMBNAIL
        ).filename,
    }
    assert len(names) == 6
    assert CacheKey(FileState.of(path), Rotation.R0, Kind.THUMBNAIL).filename == key.filename


def test_disk_limit_deletes_the_least_recently_used_first(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path / "cache", 10**9)
    image = pseudo_photo(256, 171)
    keys = [CacheKey(FileState(f"/fotos/{i}.jpg", 1, 1), Rotation.R0, Kind.THUMBNAIL) for i in range(10)]
    base = time.time() - 1000
    for i, key in enumerate(keys):
        cache.write(key, image, 90)
        # Explicit times: on Windows, files written in the same clock tick share their time.
        os.utime(tmp_path / "cache" / key.filename, (base + i, base + i))
    size = cache.total_bytes // 10
    assert cache.read(keys[0]) is not None  # used again: now the most recent
    limited = DiskCache(tmp_path / "cache", 10**9)
    assert limited.total_bytes == cache.total_bytes  # the index is rebuilt from the directory
    small = DiskCache(tmp_path / "cache", int(size * 6.5))
    assert small.total_bytes <= int(size * 6.5)
    kept = {p.name for p in _cache_files(tmp_path / "cache")}
    assert kept == {k.filename for k in [keys[0], *keys[5:]]}
    # Writing more evicts the oldest ones again.
    small.write(CacheKey(FileState("/fotos/nova.jpg", 1, 1), Rotation.R0, Kind.THUMBNAIL), image, 90)
    assert small.total_bytes <= int(size * 6.5)
    assert not (tmp_path / "cache" / keys[5].filename).exists()
    assert (tmp_path / "cache" / keys[0].filename).exists()


def test_service_respects_the_configured_limit(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    paths = copies(write_jpeg(tmp_path / "base.jpg", pseudo_photo(600, 400)), tmp_path / "fotos", 40)
    limit = 200_000
    service = make_service(source, disk_limit_bytes=limit)
    _request_all(service, paths)
    for path in paths[:5]:
        service.get_intermediate(photo_for(path))
    total = sum(p.stat().st_size for p in _cache_files(tmp_path / "cache"))
    assert 0 < total <= limit
    assert service.disk_cache.total_bytes == total


def test_other_files_in_the_cache_folder_are_never_touched(tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    foreign = [folder / "abc.pcm", folder / "notes.txt", folder / "0123456789abcdef.thumb.jpg"]
    for path in foreign:
        path.write_bytes(b"x" * 50_000)
    cache = DiskCache(folder, 1)
    cache.write(CacheKey(FileState("/a.jpg", 1, 1), Rotation.R0, Kind.THUMBNAIL), pseudo_photo(64, 64), 90)
    assert all(path.exists() for path in foreign)
    assert cache.total_bytes == 0


def test_corrupt_cache_file_is_regenerated(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "foto.jpg", pseudo_photo(1200, 800))
    _request_all(make_service(source), [path])
    (cached,) = _cache_files(tmp_path / "cache")
    cached.write_bytes(b"not a jpeg")
    result = _request_all(make_service(source), [path]).results["foto.jpg"]
    assert result is not None and result.shape == (171, 256, 3)
    assert len(source.calls) == 2


def test_unicode_cache_folder_and_photo_paths(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "Fotos d'estiu" / "Mònica à l'Empordà.jpg", pseudo_photo(800, 600))
    cache_dir = tmp_path / "Usuària Çà" / "memòria cau"
    service = make_service(source, cache_dir)
    result = _request_all(service, [path]).results[path.name]
    assert result is not None
    assert service.get_intermediate(photo_for(path)).shape == (600, 800, 3)
    assert len(_cache_files(cache_dir)) == 2


def test_unwritable_cache_still_gives_images(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    blocker = tmp_path / "no_es_carpeta"
    blocker.write_bytes(b"")  # a file where the cache folder should be
    path = write_jpeg(tmp_path / "foto.jpg", pseudo_photo(800, 600))
    service = make_service(source, blocker / "cache")
    assert _request_all(service, [path]).results["foto.jpg"] is not None
    assert service.get_intermediate(photo_for(path)).shape == (600, 800, 3)


def test_leftover_temporary_files_are_removed(tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    stale = folder / f".0123456789abcdef-0123456789ab.thumb.jpg.{'a' * 32}.tmp"
    recent = folder / f".0123456789abcdef-0123456789ab.thumb.jpg.{'b' * 32}.tmp"
    stale.write_bytes(b"x")
    recent.write_bytes(b"x")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    assert DiskCache(folder, 10**6).total_bytes == 0
    assert not stale.exists() and recent.exists()


def test_duplicated_photo_with_two_rotations_keeps_both_entries(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    """A duplicated photo rotated in only one copy: neither copy may push the other out of the cache."""
    path = write_jpeg(tmp_path / "foto.jpg", pseudo_photo(1200, 800))
    service = make_service(source)
    upright, rotated = photo_for(path, photo_id="a"), photo_for(path, Rotation.R90, photo_id="b")
    for _ in range(3):
        for photo in (upright, rotated):
            collector = Collector()
            service.request_thumbnail(photo, Priority.VISIBLE, collector)
            assert collector.wait(1)
            service.get_intermediate(photo)
    assert len(source.calls) == 4  # one thumbnail and one intermediate per rotation
    assert len(_cache_files(tmp_path / "cache")) == 4
