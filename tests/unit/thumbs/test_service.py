"""B5: ThumbnailService requests, priorities, cancellation and intermediates."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from passimaker.common import RGBImage
from passimaker.images import ImageDecodeError
from passimaker.images.decode import decode
from passimaker.model.types import Rotation
from passimaker.thumbs import INTERMEDIATE_SIZE, THUMBNAIL_SIZE, Priority
from tests.unit.images.helpers import mean_abs_diff
from tests.unit.thumbs.conftest import ServiceFactory
from tests.unit.thumbs.helpers import Collector, RecordingSource, copies, photo_for, pseudo_photo, write_jpeg


def _thumbnail(
    make_service: ServiceFactory, source: RecordingSource, path: Path, rotation: Rotation = Rotation.R0
) -> RGBImage | None:
    service = make_service(source)
    collector = Collector()
    service.request_thumbnail(photo_for(path, rotation), Priority.VISIBLE, collector)
    assert collector.wait(1)
    return next(iter(collector.results.values()))


def test_thumbnail_long_side_is_256_and_keeps_the_proportions(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "gran.jpg", pseudo_photo(3000, 2000))
    image = _thumbnail(make_service, source, path)
    assert image is not None
    assert image.shape == (171, THUMBNAIL_SIZE, 3) and image.dtype == np.uint8
    assert not image.flags.writeable
    expected = np.asarray(Image.fromarray(decode(path, 3000)[0]).resize((256, 171), Image.Resampling.BOX))
    assert mean_abs_diff(image, expected) < 3


def test_small_photo_is_not_enlarged(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "petita.jpg", pseudo_photo(120, 90))
    image = _thumbnail(make_service, source, path)
    assert image is not None and image.shape == (90, 120, 3)


def test_manual_rotation_is_applied(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "girada.jpg", pseudo_photo(800, 400))
    image = _thumbnail(make_service, source, path, rotation=Rotation.R90)
    assert image is not None and image.shape == (256, 128, 3)


def test_callback_runs_on_a_worker_thread(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "a.jpg", pseudo_photo(400, 300))
    service = make_service(source)
    collector = Collector()
    service.request_thumbnail(photo_for(path), Priority.NORMAL, collector)
    assert collector.wait(1)
    assert threading.get_ident() not in collector.threads


def test_missing_and_corrupt_files_give_none(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    good = write_jpeg(tmp_path / "bona.jpg", pseudo_photo(400, 300))
    broken = tmp_path / "tallada.jpg"
    broken.write_bytes(good.read_bytes()[:300])
    service = make_service(source)
    collector = Collector()
    missing = photo_for(tmp_path / "no_hi_es.jpg")
    service.request_thumbnail(missing, Priority.VISIBLE, collector)
    service.request_thumbnail(photo_for(broken), Priority.VISIBLE, collector)
    service.request_thumbnail(photo_for(good), Priority.VISIBLE, collector)
    assert collector.wait(3)
    assert collector.results["no_hi_es.jpg"] is None
    assert collector.results["tallada.jpg"] is None
    assert collector.results["bona.jpg"] is not None
    with pytest.raises(ImageDecodeError) as error:
        service.get_intermediate(missing)
    assert error.value.message_key == "images.not_found"


def test_duplicated_photos_share_the_work(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "a.jpg", pseudo_photo(400, 300))
    held = RecordingSource(hold_first=True)
    try:
        service = make_service(held, workers=1)
        collector = Collector()
        service.request_thumbnail(photo_for(path, photo_id="p1"), Priority.NORMAL, collector)
        assert held.entered.wait(5)
        service.request_thumbnail(photo_for(path, photo_id="p2"), Priority.NORMAL, collector)
        held.release.set()
        assert collector.wait(2)
        assert sorted(collector.order) == ["p1", "p2"]
        assert len(held.calls) == 1
    finally:
        held.close()


def test_visible_requests_are_served_first_and_can_be_promoted(
    tmp_path: Path, make_service: ServiceFactory
) -> None:
    paths = copies(write_jpeg(tmp_path / "base.jpg", pseudo_photo(300, 200)), tmp_path / "fotos", 27)
    held = RecordingSource(hold_first=True)
    try:
        service = make_service(held, workers=1)
        collector = Collector()
        photos = [photo_for(path, photo_id=f"p{i:02d}") for i, path in enumerate(paths)]
        service.request_thumbnail(photos[0], Priority.NORMAL, collector)
        assert held.entered.wait(5)
        for photo in photos[1:21]:
            service.request_thumbnail(photo, Priority.NORMAL, collector)
        for photo in photos[21:26]:
            service.request_thumbnail(photo, Priority.VISIBLE, collector)
        service.request_thumbnail(photos[10], Priority.VISIBLE, collector)  # scrolled into view
        service.request_thumbnail(photos[22], Priority.NORMAL, collector)  # never demoted
        held.release.set()
        assert collector.wait(28)
        expected_start = ["p00", "p21", "p22", "p22", "p23", "p24", "p25", "p10", "p10"]
        assert collector.order[: len(expected_start)] == expected_start
        normal = [p for p in collector.order[len(expected_start) :] if p != "p26"]
        assert normal == [f"p{i:02d}" for i in range(1, 21) if i != 10]
    finally:
        held.close()


def test_cancel_stops_pending_work_quickly(tmp_path: Path, make_service: ServiceFactory) -> None:
    paths = copies(write_jpeg(tmp_path / "base.jpg", pseudo_photo(300, 200)), tmp_path / "fotos", 300)
    # The photos are made first: photo_for reads each file's header, and where opening a file is slow
    # (an antivirus on Windows) the workers used to finish 140 thumbnails while the requests were made.
    photos = [photo_for(path, photo_id=f"p{i}") for i, path in enumerate(paths)]
    slow = RecordingSource(delay_s=0.02)
    try:
        service = make_service(slow, workers=2)
        collector = Collector()
        for photo in photos:
            service.request_thumbnail(photo, Priority.NORMAL, collector)
        assert collector.wait(10)
        start = time.perf_counter()
        service.cancel_pending()
        assert service.wait_idle(0.2), "cancel_pending ha trigat més de 200 ms"
        assert time.perf_counter() - start < 0.2
        settled = len(collector.order)
        calls = len(slow.calls)
        time.sleep(0.2)
        assert len(collector.order) == settled
        assert len(slow.calls) == calls
        assert settled < 50
        # The service keeps working after a cancel.
        service.request_thumbnail(photo_for(paths[-1], photo_id="last"), Priority.VISIBLE, collector)
        assert service.wait_idle(5)
        assert collector.results["last"] is not None
    finally:
        slow.close()


def test_close_stops_the_workers_and_ignores_new_requests(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    paths = copies(write_jpeg(tmp_path / "base.jpg", pseudo_photo(300, 200)), tmp_path / "fotos", 50)
    service = make_service(source)
    collector = Collector()
    for path in paths:
        service.request_thumbnail(photo_for(path), Priority.NORMAL, collector)
    service.close()
    service.close()
    settled = len(collector.order)
    service.request_thumbnail(photo_for(paths[0]), Priority.VISIBLE, collector)
    time.sleep(0.1)
    assert len(collector.order) == settled
    assert not any(t.is_alive() for t in threading.enumerate() if t.name.startswith("passimaker-thumbs"))


def test_a_failing_callback_does_not_stop_the_service(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    paths = copies(write_jpeg(tmp_path / "base.jpg", pseudo_photo(300, 200)), tmp_path / "fotos", 3)
    service = make_service(source, workers=1)

    def failing(photo_id: str, image: object) -> None:
        raise RuntimeError("UI bug")

    collector = Collector()
    service.request_thumbnail(photo_for(paths[0]), Priority.NORMAL, failing)
    service.request_thumbnail(photo_for(paths[1]), Priority.NORMAL, collector)
    assert collector.wait(1)


def test_intermediate_long_side_is_1600(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    big = write_jpeg(tmp_path / "gran.jpg", pseudo_photo(4000, 3000))
    small = write_jpeg(tmp_path / "petita.jpg", pseudo_photo(1200, 900))
    service = make_service(source)
    image = service.get_intermediate(photo_for(big))
    assert image.shape == (1200, INTERMEDIATE_SIZE, 3)
    assert not image.flags.writeable
    expected = np.asarray(Image.fromarray(decode(big, 4000)[0]).resize((1600, 1200), Image.Resampling.BOX))
    assert mean_abs_diff(image, expected) < 2
    assert service.get_intermediate(photo_for(small)).shape == (900, 1200, 3)
    # Second time from disk: no decoding, (almost) the same pixels.
    calls = len(source.calls)
    again = service.get_intermediate(photo_for(big))
    assert len(source.calls) == calls
    assert mean_abs_diff(again, image) < 1.5


def test_intermediate_is_made_once_for_concurrent_callers(
    tmp_path: Path, make_service: ServiceFactory
) -> None:
    path = write_jpeg(tmp_path / "gran.jpg", pseudo_photo(3000, 2000))
    slow = RecordingSource(delay_s=0.1)
    try:
        service = make_service(slow)
        photo = photo_for(path)
        with ThreadPoolExecutor(6) as pool:
            images = list(pool.map(lambda _: service.get_intermediate(photo), range(6)))
        assert len(slow.calls) == 1
        assert all(image.shape == (1067, 1600, 3) for image in images)
    finally:
        slow.close()


def test_png_thumbnail_also_stores_the_intermediate(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = tmp_path / "foto.png"
    Image.fromarray(pseudo_photo(2400, 1800)).save(path, compress_level=1)
    service = make_service(source)
    collector = Collector()
    service.request_thumbnail(photo_for(path), Priority.VISIBLE, collector)
    assert collector.wait(1)
    assert source.calls == [("foto.png", INTERMEDIATE_SIZE)]
    assert service.get_intermediate(photo_for(path)).shape == (1200, 1600, 3)
    assert len(source.calls) == 1


def test_thumbnail_reuses_an_existing_intermediate(
    tmp_path: Path, make_service: ServiceFactory, source: RecordingSource
) -> None:
    path = write_jpeg(tmp_path / "gran.jpg", pseudo_photo(3000, 2000))
    service = make_service(source)
    service.get_intermediate(photo_for(path))
    collector = Collector()
    service.request_thumbnail(photo_for(path), Priority.VISIBLE, collector)
    assert collector.wait(1)
    assert len(source.calls) == 1
    image = collector.results["gran.jpg"]
    assert image is not None and image.shape == (171, 256, 3)


def test_works_as_the_compositor_intermediate_provider(tmp_path: Path, make_service: ServiceFactory) -> None:
    from passimaker.images import CachedImageSource
    from passimaker.render import Compositor, IntermediateProvider
    from passimaker.timeline import compute_timeline
    from tests.visual.helpers import build_project, psnr

    path = write_jpeg(tmp_path / "foto.jpg", pseudo_photo(4000, 3000))
    project = build_project([photo_for(path, photo_id="p1")])
    timeline = compute_timeline(project)
    images = CachedImageSource()
    service = make_service(images)
    calls: list[str] = []

    def provider(photo: object) -> object:
        calls.append("x")
        return service.get_intermediate(photo)  # type: ignore[arg-type]

    typed: IntermediateProvider = provider  # type: ignore[assignment]
    with_intermediate = Compositor(project, timeline, images, typed)
    direct = Compositor(project, timeline, images)
    t = timeline.slots[0].visible_start + 0.5
    a = with_intermediate.frame_at(t, 960, 540)
    b = direct.frame_at(t, 960, 540)
    assert calls
    assert psnr(a, b) > 35
    images.close()
