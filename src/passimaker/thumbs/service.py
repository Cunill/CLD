"""ThumbnailService: thumbnails in background threads (visible ones first) and blocking intermediates."""

from __future__ import annotations

import heapq
import itertools
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from passimaker.common import RGBImage
from passimaker.images import ImageSource
from passimaker.model.types import Photo, Rotation
from passimaker.thumbs.disk import CacheKey, DiskCache, FileState, Kind
from passimaker.thumbs.exif import probe
from passimaker.thumbs.params import (
    DEFAULT_DISK_LIMIT_BYTES,
    DEFAULT_WORKERS,
    INTERMEDIATE_JPEG_QUALITY,
    INTERMEDIATE_SIZE,
    REDUCED_DECODE_FORMATS,
    THUMBNAIL_JPEG_QUALITY,
    THUMBNAIL_SIZE,
)

_log = logging.getLogger(__name__)

_CLOSE_JOIN_TIMEOUT_S = 1.0


class Priority(Enum):
    VISIBLE = 0
    NORMAL = 1


type ThumbnailCallback = Callable[[str, RGBImage | None], None]
"""Called as callback(photo_id, image) from a worker thread; image is None on failure."""

type _TaskKey = tuple[str, Rotation]


@dataclass(slots=True)
class _Task:
    photo: Photo
    priority: Priority
    entry: int
    """Sequence number of the heap entry that is valid for this task (older entries are skipped)."""
    queued: bool = True
    callbacks: list[tuple[str, ThumbnailCallback]] = field(default_factory=lambda: [])


def _read_only(image: RGBImage) -> RGBImage:
    image.setflags(write=False)
    return image


def fit_long_side(image: RGBImage, long_side: int) -> RGBImage:
    """Reduces the image (area filter) so that its long side is at most `long_side`."""
    height, width = image.shape[:2]
    if max(width, height) <= long_side:
        return image
    scale = long_side / max(width, height)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized: Any = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    result: RGBImage = np.ascontiguousarray(resized, dtype=np.uint8)
    return result


def _task_key(photo: Photo) -> _TaskKey:
    absolute = os.path.abspath(photo.path)  # noqa: PTH100 (no disk access on the UI thread)
    return os.path.normcase(absolute), photo.rotation


class ThumbnailService:
    """Generates thumbnails (256 px) and intermediates (1600 px) in background threads and
    stores them in a disk cache keyed by path + modification time + size. No Qt.

    - request_thumbnail never blocks: all disk access happens in the worker threads, and the
      callback is always called from a worker thread (never from inside request_thumbnail).
      Requests for the same file (e.g. duplicated photos) share the work; each callback gets its
      own photo id. VISIBLE requests are served before NORMAL ones; asking again with VISIBLE
      promotes a queued NORMAL request.
    - cancel_pending drops the queued requests and silences the callbacks of the ones running;
      no new work starts afterwards. A running request finishes its photo and stores it on disk.
    - get_intermediate blocks the calling thread (it may be called from several threads).
    - Images returned are read-only (a thumbnail may be shared by several callbacks).
    - Only files with this service's naming pattern are kept in cache_dir; when they exceed
      disk_limit_bytes, the least recently used are deleted first.
    """

    def __init__(
        self,
        cache_dir: Path,
        image_source: ImageSource,
        disk_limit_bytes: int = DEFAULT_DISK_LIMIT_BYTES,
        *,
        workers: int = DEFAULT_WORKERS,
    ) -> None:
        self._disk = DiskCache(cache_dir, disk_limit_bytes)
        self._images = image_source
        self._cond = threading.Condition()
        self._heap: list[tuple[int, int, _TaskKey]] = []
        self._tasks: dict[_TaskKey, _Task] = {}
        self._sequence = itertools.count()
        self._closed = False
        self._intermediates: dict[CacheKey, Future[RGBImage]] = {}
        self._intermediates_lock = threading.Lock()
        self._threads = [
            threading.Thread(target=self._work, name=f"passimaker-thumbs-{i}", daemon=True)
            for i in range(max(1, workers))
        ]
        for thread in self._threads:
            thread.start()

    @property
    def disk_cache(self) -> DiskCache:
        """For diagnostics and tests."""
        return self._disk

    @property
    def pending_count(self) -> int:
        """Thumbnail requests queued or running."""
        with self._cond:
            return len(self._tasks)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Waits until no thumbnail request is queued or running; False on timeout."""
        with self._cond:
            return self._cond.wait_for(lambda: not self._tasks, timeout)

    def request_thumbnail(self, photo: Photo, priority: Priority, callback: ThumbnailCallback) -> None:
        key = _task_key(photo)
        with self._cond:
            if self._closed:
                return
            task = self._tasks.get(key)
            if task is None:
                task = _Task(photo, priority, next(self._sequence))
                self._tasks[key] = task
                heapq.heappush(self._heap, (priority.value, task.entry, key))
                self._cond.notify()
            elif task.queued and priority.value < task.priority.value:
                task.priority = priority
                task.entry = next(self._sequence)
                heapq.heappush(self._heap, (priority.value, task.entry, key))
            task.callbacks.append((photo.id, callback))

    def get_intermediate(self, photo: Photo) -> RGBImage:
        """Blocking; returns the 1600 px intermediate (generating it if needed).

        Raises ImageDecodeError when the photo cannot be read."""
        key = CacheKey(FileState.of(photo.path), photo.rotation, Kind.INTERMEDIATE)
        cached = self._disk.read(key)
        if cached is not None:
            return _read_only(cached)
        return self._shared_intermediate(photo, key)

    def _shared_intermediate(self, photo: Photo, key: CacheKey) -> RGBImage:
        """Makes the intermediate once even if several threads ask for it at the same time."""
        with self._intermediates_lock:
            future = self._intermediates.get(key)
            owner = future is None
            if future is None:
                future = Future[RGBImage]()
                self._intermediates[key] = future
        if not owner:
            return future.result()
        try:
            image = self._make_intermediate(photo, key)
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(image)
            return image
        finally:
            with self._intermediates_lock:
                del self._intermediates[key]

    def cancel_pending(self) -> None:
        with self._cond:
            for key, task in list(self._tasks.items()):
                if task.queued:
                    del self._tasks[key]
                else:
                    task.callbacks.clear()
            self._heap.clear()
            self._cond.notify_all()

    def close(self) -> None:
        """Stops the workers; pending callbacks are not called. Safe to call more than once."""
        with self._cond:
            if self._closed:
                return
            self._closed = True
        self.cancel_pending()
        current = threading.current_thread()
        for thread in self._threads:
            if thread is not current:
                thread.join(_CLOSE_JOIN_TIMEOUT_S)

    # Worker side

    def _next_task(self) -> tuple[_TaskKey, _Task] | None:
        with self._cond:
            while True:
                if self._closed:
                    return None
                while self._heap:
                    _, entry, key = heapq.heappop(self._heap)
                    task = self._tasks.get(key)
                    if task is not None and task.queued and task.entry == entry:
                        task.queued = False
                        return key, task
                self._cond.wait()

    def _work(self) -> None:
        while True:
            item = self._next_task()
            if item is None:
                return
            key, task = item
            image: RGBImage | None
            try:
                image = self._make_thumbnail(task.photo)
            except Exception as exc:
                key_text = getattr(exc, "message_key", type(exc).__name__)
                _log.info("No thumbnail for %s: %s", task.photo.path, key_text)
                image = None
            with self._cond:
                callbacks = list(task.callbacks)
                if self._tasks.get(key) is task:
                    del self._tasks[key]
                self._cond.notify_all()
            for photo_id, callback in callbacks:
                try:
                    callback(photo_id, image)
                except Exception:
                    _log.exception("Thumbnail callback failed for %s", photo_id)

    def _make_thumbnail(self, photo: Photo) -> RGBImage:
        file = FileState.of(photo.path)
        thumb_key = CacheKey(file, photo.rotation, Kind.THUMBNAIL)
        cached = self._disk.read(thumb_key)
        if cached is not None:
            return _read_only(cached)
        inter_key = CacheKey(file, photo.rotation, Kind.INTERMEDIATE)
        source = self._disk.read(inter_key)
        if source is None:
            info = probe(photo.path, photo.rotation)
            if info.embedded is not None:
                source = info.embedded
            elif info.format in REDUCED_DECODE_FORMATS:
                source = self._images.get_image(photo, THUMBNAIL_SIZE)
            else:  # the whole photo is decoded anyway: keep the intermediate too
                source = self._shared_intermediate(photo, inter_key)
        thumbnail = fit_long_side(source, THUMBNAIL_SIZE)
        self._disk.write(thumb_key, thumbnail, THUMBNAIL_JPEG_QUALITY)
        return _read_only(thumbnail)

    def _make_intermediate(self, photo: Photo, key: CacheKey) -> RGBImage:
        intermediate = fit_long_side(self._images.get_image(photo, INTERMEDIATE_SIZE), INTERMEDIATE_SIZE)
        self._disk.write(key, intermediate, INTERMEDIATE_JPEG_QUALITY)
        if intermediate.flags.writeable:
            return _read_only(intermediate)
        return intermediate
