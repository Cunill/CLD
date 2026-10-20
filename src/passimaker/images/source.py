"""ImageSource protocol and its implementation with a bounded LRU memory cache."""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from passimaker.common import PassiMakerError, RGBImage
from passimaker.images.decode import ImageReadError, decode
from passimaker.model.types import Photo, Rotation

DEFAULT_MEMORY_BUDGET_BYTES = 768 * 1024 * 1024

_log = logging.getLogger(__name__)


class ImageDecodeError(PassiMakerError):
    """The file could not be decoded (corrupt, unsupported or missing).

    message_key: images.not_found, images.corrupt, images.unsupported, images.too_large or
    images.out_of_memory."""


class ImageSource(Protocol):
    """Provides oriented sRGB images at (at least) the requested size."""

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        """Returns the photo with EXIF orientation and manual rotation applied, converted to
        sRGB RGB 8-bit, with its long side >= min_long_side (or the original size if smaller)
        and at most about twice that. Raises ImageDecodeError on failure."""
        ...

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        """Starts decoding in background threads; returns immediately."""
        ...


@dataclass(frozen=True, slots=True)
class _FileKey:
    """Identifies the file contents: a modified file is a different key."""

    path: str
    mtime_ns: int
    size: int


type _PhotoKey = tuple[_FileKey, Rotation]
type _EntryKey = tuple[_FileKey, Rotation, int]


@dataclass(frozen=True, slots=True)
class _Entry:
    image: RGBImage
    long_side: int
    complete: bool
    """True when this is the original size (it then serves any larger request too)."""


def _file_key(path: Path) -> _FileKey:
    try:
        stat = path.stat()
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ImageDecodeError("images.not_found", str(path)) from exc
    except OSError as exc:
        raise ImageDecodeError("images.corrupt", f"{path}: {exc}") from exc
    absolute = os.path.abspath(path)  # noqa: PTH100 (no disk access, unlike resolve)
    return _FileKey(os.path.normcase(absolute), stat.st_mtime_ns, stat.st_size)


def _read_only(image: RGBImage) -> RGBImage:
    image.setflags(write=False)
    return image


def _downscale(image: RGBImage, long_side: int) -> RGBImage:
    height, width = image.shape[:2]
    scale = long_side / max(width, height)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized: Any = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(resized, dtype=np.uint8)


class CachedImageSource:
    """ImageSource implementation with reduced decoding and an LRU memory budget.

    - Thread-safe: get_image may be called from any thread. Two requests for the same image
      at the same time decode it only once.
    - Images are cached by file (path, modification time and size), manual rotation and size.
      A cached image serves any request between half its size and its size; a larger cached
      image is reduced instead of decoding the file again.
    - The arrays returned are shared with the cache and therefore read-only.
    - The total size of the cached arrays never exceeds `memory_budget_bytes`; the least
      recently used images are dropped first. An image larger than the budget is returned
      but not kept.
    """

    def __init__(self, memory_budget_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES, workers: int = 2) -> None:
        self._budget = max(0, int(memory_budget_bytes))
        self._lock = threading.Lock()
        self._entries: OrderedDict[_EntryKey, _Entry] = OrderedDict()
        self._sizes: dict[_PhotoKey, set[int]] = {}
        self._cached_bytes = 0
        self._inflight: dict[_EntryKey, Future[RGBImage]] = {}
        self._executor: ThreadPoolExecutor | None = ThreadPoolExecutor(
            max_workers=max(1, workers), thread_name_prefix="passimaker-images"
        )
        self.decode_count = 0
        """Number of files decoded so far (for tests and diagnostics)."""

    @property
    def cached_bytes(self) -> int:
        with self._lock:
            return self._cached_bytes

    @property
    def memory_budget_bytes(self) -> int:
        return self._budget

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        target = max(1, int(min_long_side))
        file_key = _file_key(photo.path)
        photo_key: _PhotoKey = (file_key, photo.rotation)
        request: _EntryKey = (file_key, photo.rotation, target)
        while True:
            with self._lock:
                found = self._find(photo_key, target)
                pending = None if found is not None else self._inflight.get(request)
                if found is None and pending is None:
                    future: Future[RGBImage] = Future()
                    self._inflight[request] = future
                    break
            if found is not None:
                entry, exact = found
                if exact:
                    return entry.image
                return self._store(photo_key, _read_only(_downscale(entry.image, target)), complete=False)
            assert pending is not None
            try:
                return pending.result()
            except ImageDecodeError:
                raise
            except Exception:  # the owner thread failed in an unexpected way: try again here
                continue
        try:
            image, complete = self._decode(photo.path, target, photo.rotation)
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(request, None)
            future.set_exception(exc)
            raise
        stored = self._store(photo_key, _read_only(image), complete=complete)
        with self._lock:
            self._inflight.pop(request, None)
        future.set_result(stored)
        return stored

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        with self._lock:
            executor = self._executor
        if executor is None:
            return
        for photo in photos:
            try:
                executor.submit(self._prefetch_one, photo, min_long_side)
            except RuntimeError:  # closed meanwhile
                return

    def close(self) -> None:
        """Stops the background workers (pending prefetches are dropped) and empties the cache."""
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            self._entries.clear()
            self._sizes.clear()
            self._cached_bytes = 0

    def _prefetch_one(self, photo: Photo, min_long_side: int) -> None:
        try:
            self.get_image(photo, min_long_side)
        except ImageDecodeError as exc:
            _log.info("prefetch failed for %s: %s", photo.path, exc.message_key)
        except Exception:
            _log.exception("prefetch failed for %s", photo.path)

    def _decode(self, path: Path, target: int, rotation: Rotation) -> tuple[RGBImage, bool]:
        with self._lock:
            self.decode_count += 1
        try:
            return decode(path, target, rotation)
        except ImageReadError as exc:
            raise ImageDecodeError(f"images.{exc.reason}", f"{path}: {exc.detail}") from exc

    def _find(self, photo_key: _PhotoKey, target: int) -> tuple[_Entry, bool] | None:
        """Under the lock: the best cached image for `target` and whether it can be used as is."""
        sizes = self._sizes.get(photo_key)
        if not sizes:
            return None
        usable: list[int] = []
        for long_side in sizes:
            entry = self._entries[(*photo_key, long_side)]
            if long_side >= target or entry.complete:
                usable.append(long_side)
        if not usable:
            return None
        best = min(usable)
        key: _EntryKey = (*photo_key, best)
        self._entries.move_to_end(key)
        return self._entries[key], best <= 2 * target

    def _store(self, photo_key: _PhotoKey, image: RGBImage, *, complete: bool) -> RGBImage:
        long_side = max(image.shape[:2])
        key: _EntryKey = (*photo_key, long_side)
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key].image
            if image.nbytes > self._budget:
                return image
            while self._entries and self._cached_bytes + image.nbytes > self._budget:
                old_key, old = self._entries.popitem(last=False)
                self._cached_bytes -= old.image.nbytes
                old_photo: _PhotoKey = (old_key[0], old_key[1])
                old_sizes = self._sizes[old_photo]
                old_sizes.discard(old_key[2])
                if not old_sizes:
                    del self._sizes[old_photo]
            self._entries[key] = _Entry(image, long_side, complete)
            self._sizes.setdefault(photo_key, set()).add(long_side)
            self._cached_bytes += image.nbytes
            return image
