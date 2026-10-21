"""Disk cache of thumbnails and intermediates: JPEG files with a size limit (least recently used first).

Only files whose name matches this module's pattern are ever listed, counted or deleted, so the
cache directory can be shared with other caches (e.g. the decoded audio of passimaker.audio).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from passimaker.common import RGBImage
from passimaker.images import ImageDecodeError
from passimaker.model.types import Rotation
from passimaker.thumbs.params import CACHE_FORMAT_VERSION

_log = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[0-9a-f]{16}-[0-9a-f]{12}\.(thumb|inter)\.jpg$")
_TEMP_RE = re.compile(r"^\.[0-9a-f]{16}-[0-9a-f]{12}\.(thumb|inter)\.jpg\.[0-9a-f]{32}\.tmp$")
_STALE_TEMP_S = 600.0
"""Temporary files older than this are leftovers of an interrupted write (another process may be
writing a recent one)."""


class Kind(Enum):
    THUMBNAIL = "thumb"
    INTERMEDIATE = "inter"


@dataclass(frozen=True, slots=True)
class FileState:
    """Identifies a photo file and its contents: path, modification time and size."""

    path: str
    mtime_ns: int
    size: int

    @staticmethod
    def of(path: Path) -> FileState:
        """Reads the file state; ImageDecodeError("images.not_found") if the file is missing."""
        try:
            stat = path.stat()
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise ImageDecodeError("images.not_found", str(path)) from exc
        except OSError as exc:
            raise ImageDecodeError("images.corrupt", f"{path}: {exc}") from exc
        absolute = os.path.abspath(path)  # noqa: PTH100 (no disk access, unlike resolve)
        return FileState(os.path.normcase(absolute), stat.st_mtime_ns, stat.st_size)


def _hex(text: str, length: int) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:length]


@dataclass(frozen=True, slots=True)
class CacheKey:
    file: FileState
    rotation: Rotation
    kind: Kind

    @property
    def slot(self) -> str:
        """The same for every version of the file: a new version replaces the old one."""
        return f"{_hex(self.file.path, 16)}.{self.kind.value}"

    @property
    def filename(self) -> str:
        state = _hex(
            f"{CACHE_FORMAT_VERSION}|{self.file.mtime_ns}|{self.file.size}|{self.rotation.value}", 12
        )
        return f"{_hex(self.file.path, 16)}-{state}.{self.kind.value}.jpg"


def _slot_of(name: str) -> str:
    return f"{name[:16]}.{name.rsplit('.', 2)[1]}"


def encode_jpeg(image: RGBImage, quality: int) -> bytes:
    bgr: Any = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    ok, data = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return bytes(data)


def decode_jpeg(data: bytes) -> RGBImage | None:
    """The image, or None if the data is not a valid image."""
    buffer = np.frombuffer(data, dtype=np.uint8)
    bgr: Any = cv2.imdecode(buffer, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] != 3:
        return None
    rgb: Any = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)  # pyright: ignore[reportUnknownVariableType]
    image: RGBImage = np.ascontiguousarray(rgb, dtype=np.uint8)
    return image


class DiskCache:
    """Thread-safe. Files are written atomically (temporary file + rename), so a cache shared by two
    processes never shows half-written files. The index is read from the directory on first use."""

    def __init__(self, directory: Path, limit_bytes: int) -> None:
        self._dir = directory
        self._limit = max(0, int(limit_bytes))
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, int] = OrderedDict()
        """File name -> size in bytes, least recently used first."""
        self._slots: dict[str, str] = {}
        self._total = 0
        self._loaded = False
        self._usable = True

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def limit_bytes(self) -> int:
        return self._limit

    @property
    def total_bytes(self) -> int:
        with self._lock:
            self._ensure_loaded()
            return self._total

    def read(self, key: CacheKey) -> RGBImage | None:
        """The cached image, or None. A file that cannot be decoded is deleted."""
        name = key.filename
        path = self._dir / name
        try:
            data = path.read_bytes()
        except OSError:
            with self._lock:
                self._forget(name)
            return None
        image = decode_jpeg(data)
        with self._lock:
            self._ensure_loaded()
            if image is None:
                _log.warning("Discarding unreadable cache file %s", path)
                self._forget(name)
                self._unlink(name)
                return None
            if name in self._entries:
                self._entries.move_to_end(name)
            else:  # written by another process
                self._add(name, len(data))
                self._evict()
        with contextlib.suppress(OSError):
            os.utime(path)  # the order of use survives a restart
        return image

    def write(self, key: CacheKey, image: RGBImage, quality: int) -> None:
        """Stores the image; replaces older versions of the same file; never raises."""
        name = key.filename
        with self._lock:
            self._ensure_loaded()
            if not self._usable:
                return
        try:
            data = encode_jpeg(image, quality)
            temp = self._dir / f".{name}.{uuid.uuid4().hex}.tmp"
            try:
                temp.write_bytes(data)
                temp.replace(self._dir / name)
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        except (OSError, ValueError) as exc:
            _log.warning("Cannot write cache file %s: %s", name, exc)
            return
        with self._lock:
            old = self._slots.get(key.slot)
            if old is not None and old != name:
                self._forget(old)
                self._unlink(old)
            self._forget(name)
            self._add(name, len(data))
            self._evict()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.warning("Thumbnail cache disabled, cannot create %s: %s", self._dir, exc)
            self._usable = False
            return
        found: list[tuple[int, str, int]] = []
        now = time.time()
        try:
            with os.scandir(self._dir) as listing:
                for entry in listing:
                    if _NAME_RE.match(entry.name):
                        stat = entry.stat()
                        found.append((stat.st_mtime_ns, entry.name, stat.st_size))
                    elif _TEMP_RE.match(entry.name) and now - entry.stat().st_mtime > _STALE_TEMP_S:
                        self._unlink(entry.name)
        except OSError as exc:
            _log.warning("Cannot list the thumbnail cache %s: %s", self._dir, exc)
        found.sort()
        for _, name, size in found:
            slot = _slot_of(name)
            old = self._slots.get(slot)
            if old is not None:  # two versions (e.g. a crash): keep the most recently used
                self._forget(old)
                self._unlink(old)
            self._add(name, size)
        self._evict()

    def _add(self, name: str, size: int) -> None:
        self._entries[name] = size
        self._slots[_slot_of(name)] = name
        self._total += size

    def _forget(self, name: str) -> None:
        size = self._entries.pop(name, None)
        if size is None:
            return
        self._total -= size
        slot = _slot_of(name)
        if self._slots.get(slot) == name:
            del self._slots[slot]

    def _evict(self) -> None:
        while self._total > self._limit and self._entries:
            name = next(iter(self._entries))
            self._forget(name)
            self._unlink(name)

    def _unlink(self, name: str) -> None:
        try:
            (self._dir / name).unlink(missing_ok=True)
        except OSError as exc:  # e.g. open in another program on Windows
            _log.info("Cannot delete cache file %s: %s", name, exc)
