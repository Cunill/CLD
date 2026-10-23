"""B15: failures provoked halfway through an export. The program never ends without a word: the
export finishes (with a grey photo or a silent song, and a line in the log) or stops with a
message in Catalan, and leaves no half-written video behind."""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from passimaker import images
from passimaker.common import CancelToken
from passimaker.export import ExportStatus, export_project, pipeline
from passimaker.ffmpeg._process import os_path
from passimaker.i18n import message
from passimaker.images import source as image_source
from passimaker.images.decode import REASON_OUT_OF_MEMORY, ImageReadError
from passimaker.importer import import_paths
from passimaker.model import Project
from passimaker.projectio import open_project, save_project
from tests.integration.export.conftest import ProgressLog, ffprobe, make_project

EIGHT_PHOTOS = (
    "ratio_4x3.jpg",
    "ratio_3x2.jpg",
    "ratio_16x9.jpg",
    "ratio_9x16.jpg",
    "ratio_1x1.jpg",
    "pano_3x1.jpg",
    "photo.heic",
    "orient_6.jpg",
)
MAX_CANCEL_S = 2.0

pytestmark = pytest.mark.lent


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "sortida"
    folder.mkdir()
    return folder


@pytest.fixture
def eight(fixture_files: dict[str, Path], tmp_path: Path) -> Project:
    """Photos and song are copies: the tests delete and move them."""
    (tmp_path / "musica").mkdir()
    song = shutil.copyfile(fixture_files["tone_440.wav"], tmp_path / "musica" / "tone_440.wav")
    files = {**fixture_files, "tone_440.wav": song}
    return make_project(files, tmp_path / "fotos", EIGHT_PHOTOS, ("tone_440.wav",))


def _on_first_frame(action: Callable[[], None]) -> Callable[[float, float | None], None]:
    """A progress callback that does something once, when the video frames start."""
    done = threading.Event()
    log = ProgressLog()

    def progress(fraction: float, remaining: float | None) -> None:
        log(fraction, remaining)
        if fraction > 0.2 and not done.is_set():
            done.set()
            action()

    return progress


def test_a_photo_that_disappears_during_the_export_is_drawn_grey_and_logged(
    eight: Project, out_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    last = eight.photos[-1].path
    dest = out_dir / "video.mp4"
    with caplog.at_level(logging.WARNING):
        result = export_project(eight, dest, progress=_on_first_frame(last.unlink))
    assert result.status is ExportStatus.DONE, result
    assert ffprobe(dest).audio is not None
    assert any(str(last) in record.getMessage() for record in caplog.records)


def test_a_song_that_disappears_before_its_decoding_leaves_silence_and_a_log_line(
    eight: Project, out_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    song = eight.music.songs[0].path
    moved = song.with_name("amagada.wav")
    real_prepare = pipeline.prepare

    def prepare_after_the_song_is_gone(*args: object, **kwargs: object) -> object:
        song.rename(moved)  # after the check of the missing files, as a USB stick pulled out
        return real_prepare(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(pipeline, "prepare", prepare_after_the_song_is_gone)
    dest = out_dir / "video.mp4"
    with caplog.at_level(logging.WARNING):
        result = export_project(eight, dest)
    assert result.status is ExportStatus.DONE, result
    assert any("queda en silenci" in record.getMessage() for record in caplog.records)


def test_the_destination_folder_that_disappears_stops_with_a_message(eight: Project, tmp_path: Path) -> None:
    folder = tmp_path / "llapis"
    folder.mkdir()
    dest = folder / "video.mp4"
    result = export_project(eight, dest, progress=_on_first_frame(lambda: shutil.rmtree(folder)))
    assert result.status is ExportStatus.ERROR
    assert result.reason_key is not None
    assert message(result.reason_key) != result.reason_key  # a text in Catalan exists
    assert not dest.exists()


def test_slow_reads_like_a_cloud_folder_still_cancel_quickly(
    eight: Project, out_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each photo takes a second to arrive (OneDrive, a network drive): cancelling still stops
    the export within the limit of §11."""
    real_decode = image_source.decode

    def slow_decode(*args: object, **kwargs: object) -> object:
        time.sleep(1.0)
        return real_decode(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(image_source, "decode", slow_decode)
    cancel = CancelToken()
    stopped_at: list[float] = []

    def progress(fraction: float, _remaining: float | None) -> None:
        if fraction > 0.2 and not cancel.cancelled:
            cancel.cancel()
            stopped_at.append(time.monotonic())

    dest = out_dir / "video.mp4"
    result = export_project(eight, dest, progress=progress, cancel=cancel)
    assert result.status is ExportStatus.CANCELLED
    assert stopped_at and time.monotonic() - stopped_at[0] < MAX_CANCEL_S
    assert list(out_dir.iterdir()) == []


def test_slow_reads_while_importing_still_cancel_quickly(
    fixture_files: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from passimaker.importer import scan

    folder = tmp_path / "nuvol"
    folder.mkdir()
    for i in range(40):
        shutil.copyfile(fixture_files["ratio_4x3.jpg"], folder / f"foto_{i:02d}.jpg")
    real_header = scan.read_header

    def slow_header(path: Path) -> object:
        time.sleep(0.5)
        return real_header(path)

    monkeypatch.setattr(scan, "read_header", slow_header)
    cancel = CancelToken()
    threading.Timer(0.8, cancel.cancel).start()
    start = time.monotonic()
    result = import_paths([folder], cancel=cancel)
    assert time.monotonic() - start < 0.8 + MAX_CANCEL_S
    assert result.cancelled
    assert 0 < len(result.candidates) < 40  # decision 0010: what was read is kept


def test_little_memory_while_exporting_stops_with_a_message_not_grey_photos(
    eight: Project, out_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A photo that cannot be decoded for lack of memory is not damaged: drawing it grey would
    make a wrong video without saying so. The export stops and says why, in Catalan."""
    real_decode = image_source.decode
    calls = 0

    def decode_without_memory(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls > 3:
            raise ImageReadError(REASON_OUT_OF_MEMORY)
        return real_decode(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(image_source, "decode", decode_without_memory)
    dest = out_dir / "video.mp4"
    result = export_project(eight, dest)
    assert result.status is ExportStatus.ERROR
    assert result.reason_key == "images.out_of_memory"
    assert message(result.reason_key) == "No hi ha prou memòria per obrir la foto."
    assert list(out_dir.iterdir()) == []


def test_memory_running_out_in_the_compositor_stops_with_a_message(
    eight: Project, out_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from passimaker.render import compositor

    real_build = compositor.build_canvas
    calls = 0

    def build_without_memory(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls > 3:
            raise MemoryError
        return real_build(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(compositor, "build_canvas", build_without_memory)
    result = export_project(eight, out_dir / "video.mp4")
    assert result.status is ExportStatus.ERROR
    assert result.reason_key is not None
    assert message(result.reason_key) != result.reason_key
    assert list(out_dir.iterdir()) == []


# --- Paths longer than 260 characters (MAX_PATH on Windows) -----------------------------------------


def _long_folder(base: Path) -> Path:
    folder = base / "Fotos d'en Pérez" / "àèéíòóú ïü ç ñ"
    while len(str(folder.absolute())) <= 280:
        folder = folder / "una carpeta amb un nom força llarg"
    Path(os_path(folder)).mkdir(parents=True)
    return folder


def test_photos_music_project_and_video_in_paths_longer_than_260_characters(
    fixture_files: dict[str, Path], tmp_path: Path
) -> None:
    folder = _long_folder(tmp_path)
    names = ("ratio_4x3.jpg", "photo.heic", "orient_6.jpg")
    for name in names:
        shutil.copyfile(fixture_files[name], os_path(folder / name))
    song = folder / "música" / "cançó.wav"
    Path(os_path(song.parent)).mkdir()
    shutil.copyfile(fixture_files["tone_440.wav"], os_path(song))
    assert len(str((folder / "photo.heic").absolute())) > 260

    imported = import_paths([folder / name for name in names])
    assert not imported.failures, imported.failures
    assert len(imported.candidates) == 3

    from passimaker import cli

    project = cli.new_project(folder, [song], name="llarg", seed=3)
    assert len(project.photos) == 3
    source = images.CachedImageSource()
    try:
        for photo in project.photos:
            image = source.get_image(photo, 256)
            assert image.dtype == np.uint8 and max(image.shape[:2]) >= 256
    finally:
        source.close()

    saved = folder / "projecte.pmk"
    save_project(project, saved)
    reopened = open_project(saved)
    assert reopened.missing_files == ()

    video = folder / "vídeo.mp4"
    result = export_project(reopened.project, video)
    assert result.status is ExportStatus.DONE, result
    assert Path(os_path(video)).stat().st_size > 0


def test_the_export_keeps_fewer_decoded_photos_than_the_window(
    eight: Project, out_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1,000 photos of 24 MP took the export to 1.6 GB with the 768 MB image cache of the window
    (docs/RENDIMENT.md). The export walks the photos in order: it needs far fewer at once."""
    from passimaker.export import params
    from passimaker.images import CachedImageSource
    from passimaker.images.source import DEFAULT_MEMORY_BUDGET_BYTES

    budgets: list[int] = []

    class Recording(CachedImageSource):
        def __init__(self, memory_budget_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES, workers: int = 2) -> None:
            super().__init__(memory_budget_bytes, workers)
            budgets.append(memory_budget_bytes)

    monkeypatch.setattr(pipeline, "CachedImageSource", Recording)
    result = export_project(eight, out_dir / "video.mp4")
    assert result.status is ExportStatus.DONE, result
    assert budgets == [params.IMAGE_MEMORY_BYTES]
    assert params.IMAGE_MEMORY_BYTES <= DEFAULT_MEMORY_BUDGET_BYTES // 2
