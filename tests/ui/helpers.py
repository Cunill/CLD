"""Fakes and builders for the interface tests (block B10).

The window is built with injected services so no test needs real photo files unless it is
testing the import itself: the thumbnails come from a fake that answers from worker threads,
exactly like the real service of B5, and the images from the synthetic source of B0.
"""

from __future__ import annotations

import threading
import time
import wave
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from passimaker.common import RGBImage
from passimaker.importer import FailedFile
from passimaker.model import Photo, Project, ProjectController
from passimaker.model.commands import AddPhotos
from passimaker.thumbs import INTERMEDIATE_SIZE, THUMBNAIL_SIZE, Priority, ThumbnailCallback
from passimaker.ui.duration_status import FitCheck
from passimaker.ui.music_strip import FailedSong
from passimaker.ui.project_files import SaveAnswer
from tests.fakes.images import SyntheticImageSource
from tests.fixtures.generate import synthetic_rgb

START = datetime(2026, 7, 1, 10, 0, 0)


class FakeThumbnailService:
    """Implements the part of ThumbnailService the interface uses (docs/CONTRACTES.md §4).

    Callbacks come from worker threads, as in the real service, so the tests exercise the same
    crossing between threads. `delay_s` imitates a slow disk; `broken` makes a photo fail.
    """

    def __init__(self, delay_s: float = 0.0, broken: Iterable[str] = (), workers: int = 2) -> None:
        self.delay_s = delay_s
        self.broken = set(broken)
        self.requested: list[str] = []
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fake-thumbs")
        self._cancelled = False

    def request_thumbnail(self, photo: Photo, priority: Priority, callback: ThumbnailCallback) -> None:
        with self._lock:
            if self._cancelled:
                return
            self.requested.append(photo.id)
        self._pool.submit(self._work, photo, callback)

    def _work(self, photo: Photo, callback: ThumbnailCallback) -> None:
        if self.delay_s:
            time.sleep(self.delay_s)
        callback(photo.id, None if photo.id in self.broken else thumbnail_for(photo, THUMBNAIL_SIZE))

    def get_intermediate(self, photo: Photo) -> RGBImage:
        return thumbnail_for(photo, INTERMEDIATE_SIZE)

    def cancel_pending(self) -> None:
        """Like the real service: drops what is queued, but new requests still work."""

    def close(self) -> None:
        with self._lock:
            self._cancelled = True
        self._pool.shutdown(wait=True)

    def wait(self) -> None:
        """Waits for every queued thumbnail (the tests need a settled state)."""
        self._pool.shutdown(wait=True)
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fake-thumbs")


def thumbnail_for(photo: Photo, long_side: int) -> RGBImage:
    scale = long_side / max(photo.width, photo.height)
    width = max(1, round(photo.width * min(1.0, scale)))
    height = max(1, round(photo.height * min(1.0, scale)))
    image = synthetic_rgb(width, height, abs(hash(photo.id)) % 1_000_000)
    image.setflags(write=False)
    return image


def make_photo(index: int, width: int = 1600, height: int = 1200) -> Photo:
    return Photo(
        id=f"p{index:04d}",
        path=Path(f"/fotos/IMG_{index:04d}.jpg"),
        relative_path=None,
        width=width,
        height=height,
        capture_time=START + timedelta(minutes=index),
    )


def make_photos(count: int) -> tuple[Photo, ...]:
    """Photos with a couple of proportions, so fits and motions are not all the same."""
    sizes = ((1600, 1200), (1200, 1600), (1920, 1080))
    return tuple(make_photo(i, *sizes[i % len(sizes)]) for i in range(1, count + 1))


def controller_with(count: int, project: Project | None = None) -> ProjectController:
    controller = ProjectController(project if project is not None else Project(seed=7))
    if count:
        controller.execute(AddPhotos(make_photos(count)))
    return controller


def write_photos(folder: Path, names: Sequence[str], size: tuple[int, int] = (320, 240)) -> list[Path]:
    """Small real JPEGs, for the tests that go through the real importer."""
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, name in enumerate(names):
        path = folder / name
        array = synthetic_rgb(size[0], size[1], index)
        Image.fromarray(array).save(path, quality=80)
        paths.append(path)
    return paths


def write_song(path: Path, seconds: float, frequency: float = 440.0, rate: int = 48_000) -> Path:
    """A real WAV file with a quiet tone (read by FFmpeg like any song)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(seconds * rate), dtype=np.float64) / rate
    tone = (0.2 * 32767 * np.sin(2 * np.pi * frequency * t)).astype(np.int16)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(np.repeat(tone[:, None], 2, axis=1).tobytes())
    return path


class RecordedQuestions:
    """Answers every question of the window without a dialog, and records them."""

    def __init__(
        self,
        subfolders: bool = False,
        duplicates: bool = False,
        delete: bool = True,
        photos: Sequence[Path] = (),
        folder: Path | None = None,
    ) -> None:
        self.subfolders = subfolders
        self.duplicates = duplicates
        self.delete = delete
        self.photos = list(photos)
        self.folder = folder
        self.chosen_photos = 0
        self.chosen_folders = 0
        self.asked_subfolders: list[int] = []
        self.asked_duplicates: list[int] = []
        self.asked_delete: list[int] = []
        self.failures: list[FailedFile] = []
        self.many_photos: list[int] = []
        # Music (§1.7)
        self.music: list[Path] = []
        self.song_failures: list[FailedSong] = []
        self.fit = True
        self.fit_checks: list[FitCheck] = []
        # Export (§1.9)
        self.export_path: Path | None = None
        self.suggested_exports: list[Path] = []
        self.missing_reports: list[list[Path]] = []
        # Project files (§1.10)
        self.open_path: Path | None = None
        self.save_path: Path | None = None
        self.save_answer = SaveAnswer.DISCARD
        self.asked_save: list[str] = []
        self.recover = True
        self.offered_recovery = 0
        self.relink_folder: Path | None = None
        self.asked_relink: list[int] = []
        self.relinked: list[tuple[int, int]] = []
        self.errors: list[str] = []

    def ask_subfolders(self, count: int) -> bool:
        self.asked_subfolders.append(count)
        return self.subfolders

    def ask_duplicates(self, count: int) -> bool:
        self.asked_duplicates.append(count)
        return self.duplicates

    def report_failures(self, failures: Sequence[FailedFile]) -> None:
        self.failures.extend(failures)

    def warn_many_photos(self, count: int) -> None:
        self.many_photos.append(count)

    def confirm_delete(self, count: int) -> bool:
        self.asked_delete.append(count)
        return self.delete

    def choose_photos(self) -> list[Path]:
        self.chosen_photos += 1
        return list(self.photos)

    def choose_folder(self) -> Path | None:
        self.chosen_folders += 1
        return self.folder

    def choose_music(self) -> list[Path]:
        return list(self.music)

    def report_song_failures(self, failures: Sequence[FailedSong]) -> None:
        self.song_failures.extend(failures)

    def confirm_fit(self, check: FitCheck) -> bool:
        self.fit_checks.append(check)
        return self.fit

    def choose_export_path(self, suggested: Path) -> Path | None:
        self.suggested_exports.append(suggested)
        return self.export_path

    def report_missing_files(self, paths: Sequence[Path]) -> None:
        self.missing_reports.append(list(paths))

    def choose_project_to_open(self) -> Path | None:
        return self.open_path

    def choose_project_save_path(self, suggested: Path) -> Path | None:
        return self.save_path

    def ask_save_changes(self, name: str) -> SaveAnswer:
        self.asked_save.append(name)
        return self.save_answer

    def offer_recovery(self) -> bool:
        self.offered_recovery += 1
        return self.recover

    def ask_relink(self, count: int) -> Path | None:
        self.asked_relink.append(count)
        return self.relink_folder

    def report_relinked(self, found: int, still_missing: int) -> None:
        self.relinked.append((found, still_missing))

    def show_error(self, text: str) -> None:
        self.errors.append(text)


def images() -> SyntheticImageSource:
    return SyntheticImageSource()


def as_rgb(array: object) -> RGBImage:
    assert isinstance(array, np.ndarray)
    return array
