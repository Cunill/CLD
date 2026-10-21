"""B4: import_paths — formats, failures, folders, duplicates, progress and cancellation."""

from __future__ import annotations

import contextlib
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import ImageFile

from passimaker.common import CancelToken
from passimaker.images import CachedImageSource, ImageDecodeError
from passimaker.importer import FailedFile, ImportFailure, PhotoCandidate, import_paths
from passimaker.model.types import Photo
from tests.fixtures.generate import PHOTO_SPECS
from tests.unit.images.samples import exif_bytes, pattern, write_jpeg

SUPPORTED_SAMPLES = [
    "photo.bmp",
    "orient_6.tif",
    "photo.webp",
    "animated.gif",
    "p3.jpg",
    "p3_nclx.heic",
    "rgb16.png",
    "rgb16.tif",
    "png_named.jpg",
    "just_big_enough.png",
]


def _by_name(candidates: tuple[PhotoCandidate, ...]) -> dict[str, PhotoCandidate]:
    return {c.path.name: c for c in candidates}


def _reasons(failures: tuple[FailedFile, ...]) -> dict[str, ImportFailure]:
    return {f.path.name: f.reason for f in failures}


def test_every_generated_photo_is_imported_with_its_oriented_size(fixture_files: dict[str, Path]) -> None:
    result = import_paths([fixture_files[s.name] for s in PHOTO_SPECS])
    found = _by_name(result.candidates)
    assert result.failures == () and not result.cancelled
    for spec in PHOTO_SPECS:
        candidate = found[spec.name]
        assert (candidate.width, candidate.height) == spec.oriented_size, spec.name
        assert candidate.capture_time == spec.capture_time, spec.name
    assert found["orient_6.jpg"].exif_orientation == 6
    assert found["photo.heic"].exif_orientation == 1  # libheif orients HEIF itself


def test_other_formats_are_imported(samples: dict[str, Path]) -> None:
    result = import_paths([samples[n] for n in SUPPORTED_SAMPLES])
    assert result.failures == ()
    found = _by_name(result.candidates)
    assert set(found) == set(SUPPORTED_SAMPLES)
    assert (found["orient_6.tif"].width, found["orient_6.tif"].height) == (320, 480)
    assert found["p3.jpg"].color_profile == "Display P3"
    assert found["p3_nclx.heic"].color_profile == "Display P3 (nclx)"
    assert found["photo.bmp"].color_profile is None


def test_failures_have_a_reason(
    fixture_files: dict[str, Path], samples: dict[str, Path], tmp_path: Path
) -> None:
    paths = [
        samples["camera.cr2"],
        samples["camera.dng"],
        samples["song.mp3"],
        samples["empty.jpg"],
        samples["icon_named.png"],
        samples["too_small.png"],
        fixture_files["not_an_image.jpg"],
        tmp_path / "missing.jpg",
    ]
    result = import_paths(paths)
    assert result.candidates == ()
    assert _reasons(result.failures) == {
        "camera.cr2": ImportFailure.RAW,
        "camera.dng": ImportFailure.RAW,
        "song.mp3": ImportFailure.UNSUPPORTED,
        "empty.jpg": ImportFailure.CORRUPT,
        "icon_named.png": ImportFailure.UNSUPPORTED,
        "too_small.png": ImportFailure.TOO_SMALL,
        "not_an_image.jpg": ImportFailure.CORRUPT,
        "missing.jpg": ImportFailure.NOT_FOUND,
    }


def test_damaged_pixel_data_is_reported_when_decoding(fixture_files: dict[str, Path]) -> None:
    """Only headers are read when importing; the truncated JPEG fails in passimaker.images."""
    path = fixture_files["corrupt.jpg"]
    (candidate,) = import_paths([path]).candidates
    photo = Photo("c", path, None, candidate.width, candidate.height)
    with pytest.raises(ImageDecodeError) as info:
        CachedImageSource().get_image(photo, 400)
    assert info.value.message_key == "images.corrupt"


def test_only_headers_are_read(
    monkeypatch: pytest.MonkeyPatch, fixture_files: dict[str, Path], samples: dict[str, Path]
) -> None:
    def no_pixels(self: ImageFile.ImageFile) -> None:
        raise AssertionError("pixels decoded while importing")

    monkeypatch.setattr(ImageFile.ImageFile, "load", no_pixels)
    paths = [fixture_files[s.name] for s in PHOTO_SPECS] + [samples[n] for n in SUPPORTED_SAMPLES]
    result = import_paths(paths)
    assert result.failures == ()
    assert len(result.candidates) == len(paths)


def test_garbage_never_raises(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    rng = np.random.default_rng(4)
    magic = [
        b"\xff\xd8\xff\xe0",
        b"\x89PNG\r\n\x1a\n",
        b"GIF89a",
        b"II*\x00",
        b"RIFF\0\0\0\0WEBP",
        b"\0\0\0\x18ftypheic",
    ]
    paths: list[Path] = []
    for i in range(60):
        head = magic[i % len(magic)]
        path = tmp_path / f"junk_{i}{['.jpg', '.png', '.gif', '.tif', '.webp', '.heic'][i % 6]}"
        path.write_bytes(head + rng.integers(0, 256, int(rng.integers(0, 4000)), dtype=np.uint8).tobytes())
        paths.append(path)
    for name in ["ratio_4x3.jpg", "alpha.png", "photo.heic"]:
        data = fixture_files[name].read_bytes()
        for cut in (10, 100, 400, len(data) // 2):
            path = tmp_path / f"cut{cut}_{name}"
            path.write_bytes(data[:cut])
            paths.append(path)
    result = import_paths(paths)
    assert len(result.candidates) + len(result.failures) == len(paths)
    images = CachedImageSource()
    for candidate in result.candidates:
        photo = Photo(candidate.path.name, candidate.path, None, candidate.width, candidate.height)
        with contextlib.suppress(ImageDecodeError):  # any other exception fails the test
            images.get_image(photo, 200)


# --- folders -------------------------------------------------------------------------------------


@pytest.fixture
def album(tmp_path: Path, fixture_files: dict[str, Path], samples: dict[str, Path]) -> Path:
    """album/ with 4 photos, a RAW, a song, a hidden file; album/sub/ with 2; album/sub/deeper/ with 1."""
    root = tmp_path / "àlbum d'estiu"
    deeper = root / "sub" / "deeper"
    deeper.mkdir(parents=True)
    for name in ["ratio_4x3.jpg", "ratio_3x2.jpg", "orient_6.jpg", "photo.heic"]:
        shutil.copy(fixture_files[name], root / name)
    shutil.copy(samples["camera.cr2"], root / "camera.cr2")
    shutil.copy(samples["song.mp3"], root / "song.mp3")
    shutil.copy(fixture_files["ratio_1x1.jpg"], root / ".hidden.jpg")
    (root / ".git").mkdir()
    shutil.copy(fixture_files["ratio_1x1.jpg"], root / ".git" / "inside.jpg")
    shutil.copy(fixture_files["ratio_16x9.jpg"], root / "sub" / "a.jpg")
    shutil.copy(samples["photo.bmp"], root / "sub" / "b.bmp")
    shutil.copy(samples["photo.webp"], deeper / "c.webp")
    return root


def test_a_folder_imports_its_photos_and_counts_the_subfolders(album: Path) -> None:
    result = import_paths([album])
    assert sorted(c.path.name for c in result.candidates) == [
        "orient_6.jpg",
        "photo.heic",
        "ratio_3x2.jpg",
        "ratio_4x3.jpg",
    ]
    assert _reasons(result.failures) == {"camera.cr2": ImportFailure.RAW}  # song.mp3 is skipped silently
    assert result.subfolder_photo_count == 3


def test_subfolders_can_be_included(album: Path) -> None:
    result = import_paths([album], include_subfolders=True)
    assert len(result.candidates) == 7
    assert result.subfolder_photo_count == 0


def test_the_same_file_twice_is_read_once(album: Path) -> None:
    result = import_paths([album / "ratio_4x3.jpg", album, album / "sub" / ".." / "ratio_4x3.jpg"])
    assert len(result.candidates) == 4
    assert result.duplicates == ()


def test_photos_already_in_the_project_are_duplicates(album: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(album)
    existing = frozenset({Path("ratio_4x3.jpg"), album / "sub" / ".." / "photo.heic"})
    result = import_paths([album], existing=existing)
    assert sorted(p.name for p in result.duplicates) == ["photo.heic", "ratio_4x3.jpg"]
    assert sorted(c.path.name for c in result.candidates) == ["orient_6.jpg", "ratio_3x2.jpg"]


@pytest.mark.skipif(os.name != "nt", reason="paths are case-insensitive only on Windows")
def test_duplicates_ignore_case_on_windows(album: Path) -> None:
    result = import_paths([album / "ratio_4x3.jpg"], existing=frozenset({album / "RATIO_4X3.JPG"}))
    assert len(result.duplicates) == 1


# --- order ---------------------------------------------------------------------------------------


def _set_mtime(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def _write(folder: Path, name: str, capture: str | None, mtime: datetime) -> Path:
    path = write_jpeg(folder / name, pattern(name, 160, 120), exif=exif_bytes(1, capture))
    _set_mtime(path, mtime)
    return path


def test_order_by_date_when_80_percent_have_one(tmp_path: Path) -> None:
    mtime = datetime(2020, 1, 1, 12, 0, 0)
    _write(tmp_path, "IMG_1.jpg", "2024:05:03 10:00:00", mtime)
    _write(tmp_path, "IMG_2.jpg", "2024:05:01 10:00:00", mtime)
    _write(tmp_path, "IMG_3.jpg", "2024:05:02 10:00:00", mtime)
    _write(tmp_path, "IMG_4.jpg", "2024:05:02 10:00:00", mtime)  # same time: name decides
    _write(tmp_path, "IMG_5.jpg", None, datetime(2024, 5, 1, 12, 0, 0))  # file date
    result = import_paths([tmp_path])
    assert [c.path.name for c in result.candidates] == [
        "IMG_2.jpg",
        "IMG_5.jpg",
        "IMG_3.jpg",
        "IMG_4.jpg",
        "IMG_1.jpg",
    ]


def test_order_by_natural_name_otherwise(tmp_path: Path) -> None:
    mtime = datetime(2020, 1, 1, 12, 0, 0)
    _write(tmp_path, "IMG_10.jpg", "2024:05:01 10:00:00", mtime)
    _write(tmp_path, "IMG_9.jpg", "2024:05:03 10:00:00", mtime)
    _write(tmp_path, "img_2.jpg", "2024:05:02 10:00:00", mtime)
    _write(tmp_path, "IMG_1.jpg", None, mtime)
    _write(tmp_path, "IMG_100.jpg", None, mtime)
    result = import_paths([tmp_path])  # 3 of 5 = 60 % with a date
    assert [c.path.name for c in result.candidates] == [
        "IMG_1.jpg",
        "img_2.jpg",
        "IMG_9.jpg",
        "IMG_10.jpg",
        "IMG_100.jpg",
    ]


def test_capture_time_details(tmp_path: Path) -> None:
    mtime = datetime(2021, 3, 4, 5, 6, 7)
    bad = _write(tmp_path, "zero.jpg", "0000:00:00 00:00:00", mtime)
    good = _write(tmp_path, "good.jpg", "2023:07:14 18:30:05", mtime)
    found = _by_name(import_paths([bad, good]).candidates)
    assert found["zero.jpg"].capture_time is None
    assert found["zero.jpg"].file_time == mtime
    assert found["good.jpg"].capture_time == datetime(2023, 7, 14, 18, 30, 5)


# --- progress, cancellation and speed ------------------------------------------------------------


@pytest.fixture(scope="module")
def thousand(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("thousand")
    source = write_jpeg(
        folder / "source.jpg", pattern("thousand", 400, 300), exif=exif_bytes(6, "2024:01:01 00:00:00")
    )
    for i in range(1000):
        shutil.copy(source, folder / f"IMG_{i:04}.jpg")
    source.unlink()
    return folder


def test_metadata_of_1000_files_in_less_than_10_s(thousand: Path) -> None:
    calls: list[tuple[int, int]] = []
    start = time.perf_counter()
    result = import_paths([thousand], progress=lambda done, total: calls.append((done, total)))
    elapsed = time.perf_counter() - start
    assert len(result.candidates) == 1000
    assert elapsed < 10.0, f"{elapsed:.1f} s"
    assert calls[0] == (0, 1000) and calls[-1] == (1000, 1000)
    assert [d for d, _ in calls] == sorted(d for d, _ in calls)
    assert all(total == 1000 for _, total in calls)
    assert {(c.width, c.height) for c in result.candidates} == {(300, 400)}


def test_cancelling_stops_quickly_and_keeps_what_was_read(thousand: Path) -> None:
    token = CancelToken()
    cancelled_at: list[float] = []

    def progress(done: int, total: int) -> None:
        if done >= 50 and not token.cancelled:
            token.cancel()
            cancelled_at.append(time.perf_counter())

    result = import_paths([thousand], progress=progress, cancel=token)
    assert result.cancelled
    assert 50 <= len(result.candidates) < 1000
    assert time.perf_counter() - cancelled_at[0] < 0.5
    names = [c.path.name for c in result.candidates]
    assert names == sorted(names)


def test_cancelled_before_starting(thousand: Path) -> None:
    token = CancelToken()
    token.cancel()
    result = import_paths([thousand], cancel=token)
    assert result.cancelled and result.candidates == ()


def test_nothing_to_import() -> None:
    result = import_paths([])
    assert result == type(result)((), (), (), 0, False)
