"""B5: the EXIF thumbnail embedded in JPEG files is used when it is large enough, oriented like the photo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from passimaker.images.decode import decode
from passimaker.model.types import Rotation
from passimaker.thumbs import Priority, ThumbnailService
from passimaker.thumbs.exif import probe
from passimaker.thumbs.service import fit_long_side
from tests.fixtures.generate import f_pattern
from tests.unit.images.helpers import dihedral, mean_abs_diff
from tests.unit.thumbs.conftest import ServiceFactory
from tests.unit.thumbs.helpers import Collector, RecordingSource, exif_with_thumbnail, photo_for, write_jpeg

RED = (200, 30, 30)


def _solid(width: int, height: int, colour: tuple[int, int, int] = RED) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:] = colour
    return image


def _thumbnail(service: ThumbnailService, path: Path, rotation: Rotation = Rotation.R0) -> np.ndarray:
    collector = Collector()
    service.request_thumbnail(photo_for(path, rotation), Priority.VISIBLE, collector)
    assert collector.wait(1)
    image = collector.results[path.name]
    assert image is not None
    return image


def test_large_enough_exif_thumbnail_is_used_without_decoding_the_photo(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    # The embedded thumbnail is red and the photo is green: the result shows which one was used.
    path = write_jpeg(
        tmp_path / "camera.jpg", _solid(3000, 2000, (30, 160, 60)), exif_with_thumbnail(_solid(160, 107))
    )
    image = _thumbnail(make_service(source), path)
    assert image.shape == (107, 160, 3)
    assert np.abs(image.astype(int) - RED).max() < 12
    assert source.calls == []


@pytest.mark.parametrize("big_endian", [False, True])
def test_large_exif_thumbnails_are_reduced_to_256(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource, big_endian: bool
) -> None:
    path = write_jpeg(
        tmp_path / "camera.jpg",
        _solid(4000, 3000, (30, 160, 60)),
        exif_with_thumbnail(_solid(640, 480), big_endian=big_endian),
    )
    image = _thumbnail(make_service(source), path)
    assert image.shape == (192, 256, 3)
    assert source.calls == []


@pytest.mark.parametrize(
    ("thumb_size", "reason"),
    [((128, 96), "massa petita"), ((160, 120), "franges negres: 4:3 per a una foto 3:2")],
)
def test_unsuitable_exif_thumbnail_is_ignored(
    tmp_path: Path,
    make_service: ServiceFactory,
    source: RecordingSource,
    thumb_size: tuple[int, int],
    reason: str,
) -> None:
    path = write_jpeg(
        tmp_path / "camera.jpg", _solid(3000, 2000, (30, 160, 60)), exif_with_thumbnail(_solid(*thumb_size))
    )
    image = _thumbnail(make_service(source), path)
    assert image.shape == (171, 256, 3), reason
    assert np.abs(image.astype(int) - (30, 160, 60)).max() < 12, reason
    assert len(source.calls) == 1


def test_corrupt_exif_thumbnail_falls_back_to_the_photo(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    exif = bytearray(exif_with_thumbnail(_solid(160, 107)))
    exif[-200:] = bytes(200)  # thumbnail data cut
    path = write_jpeg(tmp_path / "camera.jpg", _solid(3000, 2000, (30, 160, 60)), bytes(exif))
    image = _thumbnail(make_service(source), path)
    assert np.abs(image.astype(int) - (30, 160, 60)).max() < 12
    assert probe(tmp_path / "no_hi_es.jpg", Rotation.R0).format is None


@pytest.mark.parametrize("orientation", range(1, 9))
@pytest.mark.parametrize("rotation", [Rotation.R0, Rotation.R90])
def test_exif_thumbnail_follows_orientation_and_rotation(
    tmp_path: Path,
    make_service: ServiceFactory,
    source: RecordingSource,
    orientation: int,
    rotation: Rotation,
) -> None:
    """The stored pixels and the stored thumbnail are the same picture: after orientation (and the
    manual rotation) the thumbnail must match the decoded photo (B4, verified with the "F" test)
    better than any other rotation or mirror image of it."""
    stored = f_pattern(1200, 800)
    thumb = fit_long_side(stored, 240)
    path = write_jpeg(tmp_path / f"o{orientation}.jpg", stored, exif_with_thumbnail(thumb, orientation))
    image = _thumbnail(make_service(source), path, rotation)
    assert source.calls == []
    reference = fit_long_side(decode(path, 1200, rotation)[0], 240)
    assert image.shape == reference.shape
    assert mean_abs_diff(image, reference) < 6
    scores = [
        mean_abs_diff(candidate, reference)
        for candidate in dihedral(image)
        if candidate.shape == reference.shape
    ]
    assert int(np.argmin(scores)) == 0
