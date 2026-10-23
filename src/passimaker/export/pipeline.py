"""export_project: checks, audio, frames and encoder (docs/CONTRACTES.md §11)."""

from __future__ import annotations

import errno
import logging
import os
import tempfile
import threading
import time
from collections import deque
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from passimaker.audio import prepare
from passimaker.common import CancelToken, PassiMakerError, RGBImage
from passimaker.export.checks import estimated_video_bytes, has_room, missing_files, wav_bytes
from passimaker.export.files import long_path, remove_quietly, replace
from passimaker.export.locations import audio_cache_dir
from passimaker.export.params import CANCEL_POLL_S, FRAMES_IN_FLIGHT, IMAGE_MEMORY_BYTES, RENDER_THREADS
from passimaker.export.power import keep_awake
from passimaker.export.progress import ExportProgress, ProgressTracker
from passimaker.ffmpeg import ERROR_DISK_FULL as FFMPEG_DISK_FULL
from passimaker.ffmpeg import ERROR_WRITE as FFMPEG_WRITE
from passimaker.ffmpeg import FfmpegError, VideoWriter, locate, open_encoder
from passimaker.images import CachedImageSource, ImageDecodeError, ImageSource
from passimaker.model.types import Photo, Project
from passimaker.render import Compositor
from passimaker.timeline import Timeline, compute_timeline, frame_to_time

# Message keys (passimaker.i18n) of the export errors; FFmpeg errors keep their own ffmpeg.* key.
ERROR_NO_PHOTOS = "export.no_photos"
"""The project has no photos."""
ERROR_MISSING_FILES = "export.missing_files"
"""Some photos or songs are not found (detail: how many); the list is missing_files(project)."""
ERROR_DISK_FULL = "export.disk_full"
"""Not enough free space, before starting (estimate) or while writing."""
ERROR_WRITE = "export.write_error"
"""The video cannot be written there (missing folder, no permission, read-only drive...)."""
ERROR_FAILED = "export.failed"
"""Unexpected failure (details in the log)."""
ERROR_OUT_OF_MEMORY = "images.out_of_memory"
"""Not enough memory to open a photo (B15): the export stops instead of drawing it grey."""

PARTIAL_SUFFIX = ".part"
"""The video is written as "<name>.mp4.part" next to the destination and renamed at the end (§1.9)."""

_log = logging.getLogger(__name__)


class ExportStatus(Enum):
    DONE = "done"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ExportResult:
    status: ExportStatus
    reason_key: str | None
    """Translatable message key when status is ERROR."""
    duration_s: float
    size_bytes: int


class _ExportError(Exception):
    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key = key


class _NoMemoryForPhotoError(Exception):
    """Not a PassiMakerError on purpose: the compositor draws a photo it cannot read as a grey
    canvas, which is right for a damaged file but would hide a lack of memory in the video."""


class _ExportImages:
    """The image source of the export: a photo that fails for lack of memory stops the export."""

    def __init__(self, images: ImageSource) -> None:
        self._images = images

    def get_image(self, photo: Photo, min_long_side: int) -> RGBImage:
        try:
            return self._images.get_image(photo, min_long_side)
        except ImageDecodeError as error:
            if error.message_key == ERROR_OUT_OF_MEMORY:
                raise _NoMemoryForPhotoError(str(error)) from error
            raise

    def prefetch(self, photos: Sequence[Photo], min_long_side: int) -> None:
        self._images.prefetch(photos, min_long_side)


def export_project(
    project: Project,
    dest: Path,
    *,
    progress: ExportProgress | None = None,
    cancel: CancelToken | None = None,
    sentinel: bool = False,
) -> ExportResult:
    """Validates, renders audio, composes frames and encodes. Writes to a temporary name and
    renames at the end; never leaves a partial file. `sentinel` is for tests only.

    Blocking (minutes): call it from a worker thread. progress(fraction, seconds_remaining) is
    called from this thread, at most every 0.1 s; the fraction never goes back. Cancelling stops
    the export in less than 2 s.
    """
    cancel = cancel if cancel is not None else CancelToken()
    dest = Path(os.path.normpath(dest.absolute()))
    partial = dest.with_name(dest.name + PARTIAL_SUFFIX)
    started = time.monotonic()
    try:
        timeline = compute_timeline(project)
        duration_s = timeline.total_frames / timeline.fps
        _check(project, dest, partial, duration_s)
        tracker = ProgressTracker(progress, timeline.total_frames)
        tracker.start()
        with keep_awake():
            completed = _export(project, timeline, partial, tracker, cancel, sentinel)
        if not completed:
            _log.info("Exportació cancel·lada: %s", dest)
            return ExportResult(ExportStatus.CANCELLED, None, 0.0, 0)
        replace(partial, dest)
        tracker.finished()
        elapsed = time.monotonic() - started
        _log.info(
            "Exportat %s: %d imatges en %.1f s (%.1f imatges/s)",
            dest,
            timeline.total_frames,
            elapsed,
            timeline.total_frames / elapsed if elapsed > 0 else 0.0,
        )
        return ExportResult(ExportStatus.DONE, None, duration_s, long_path(dest).stat().st_size)
    except _ExportError as failure:
        return _error(failure.key, failure)
    except FfmpegError as error:
        return _error(_ffmpeg_key(error.message_key), error)
    except PassiMakerError as error:
        return _error(error.message_key, error)
    except OSError as error:
        return _error(ERROR_DISK_FULL if error.errno == errno.ENOSPC else ERROR_WRITE, error)
    except (_NoMemoryForPhotoError, MemoryError) as error:
        return _error(ERROR_OUT_OF_MEMORY, error)
    except Exception as error:
        _log.exception("Error inesperat en exportar %s", dest)
        return _error(ERROR_FAILED, error)
    finally:
        remove_quietly(partial)


def _error(key: str, error: BaseException) -> ExportResult:
    _log.warning("No s'ha pogut exportar (%s): %s", key, error)
    return ExportResult(ExportStatus.ERROR, key, 0.0, 0)


def _ffmpeg_key(key: str) -> str:
    return {FFMPEG_DISK_FULL: ERROR_DISK_FULL, FFMPEG_WRITE: ERROR_WRITE}.get(key, key)


# --- Before starting ------------------------------------------------------------------------------


def _check(project: Project, dest: Path, partial: Path, duration_s: float) -> None:
    """Everything that can be known before spending minutes on the export (§1.9)."""
    if not project.photos:
        raise _ExportError(ERROR_NO_PHOTOS)
    missing = missing_files(project)
    if missing:
        raise _ExportError(ERROR_MISSING_FILES, f"{len(missing)} fitxers, el primer {missing[0]}")
    if not long_path(dest.parent).is_dir() or long_path(dest).is_dir():
        raise _ExportError(ERROR_WRITE, str(dest))
    locate()  # FFmpeg missing: say so now, not after the audio
    if not has_room(dest.parent, estimated_video_bytes(duration_s)):
        raise _ExportError(ERROR_DISK_FULL, str(dest.parent))
    long_path(partial).touch()  # can we write there? (permissions, read-only drive)


# --- The export -----------------------------------------------------------------------------------


def _export(
    project: Project,
    timeline: Timeline,
    partial: Path,
    tracker: ProgressTracker,
    cancel: CancelToken,
    sentinel: bool,
) -> bool:
    """Audio into a provisional WAV, then frames into the encoder. False if cancelled."""
    with tempfile.TemporaryDirectory(prefix="passimaker-export-", ignore_cleanup_errors=True) as work:
        wav = Path(work) / "audio.wav"
        if not has_room(wav.parent, wav_bytes(timeline.total_frames / timeline.fps)):
            raise _ExportError(ERROR_DISK_FULL, str(wav.parent))
        audio = prepare(project, timeline.audio_plan, audio_cache_dir())
        for song_id, error in audio.failures.items():
            _log.warning("La cançó %s no es pot llegir i el seu lloc queda en silenci: %s", song_id, error)
        if cancel.cancelled:
            return False
        audio.render_wav(wav, tracker.audio, cancel)
        if cancel.cancelled:
            return False
        images = CachedImageSource(memory_budget_bytes=IMAGE_MEMORY_BYTES)
        completed = False
        try:
            compositor = Compositor(project, timeline, _ExportImages(images))
            width, height = project.output_format.size
            writer = open_encoder(partial, width, height, wav)
            try:
                completed = _write_frames(
                    compositor, timeline, (width, height), writer, tracker, cancel, sentinel
                ) and _close(writer, cancel)
            finally:
                if not completed:
                    writer.abort()
        finally:
            if completed:
                images.close()
            else:  # running decodes may take a moment: do not make the cancel wait for them
                threading.Thread(target=images.close, name="passimaker-export-close", daemon=True).start()
        return completed


def _write_frames(
    compositor: Compositor,
    timeline: Timeline,
    size: tuple[int, int],
    writer: VideoWriter,
    tracker: ProgressTracker,
    cancel: CancelToken,
    sentinel: bool,
) -> bool:
    """Frame n (shown at n / fps) from RENDER_THREADS threads, written in order. False if cancelled."""
    width, height = size
    total = timeline.total_frames
    pool = ThreadPoolExecutor(RENDER_THREADS, thread_name_prefix="passimaker-export")
    pending: deque[Future[RGBImage]] = deque()
    submitted = 0
    try:
        for written in range(total):
            while submitted < total and len(pending) < FRAMES_IN_FLIGHT:
                t = frame_to_time(submitted, timeline.fps)
                pending.append(pool.submit(compositor.frame_at, t, width, height, sentinel=sentinel))
                submitted += 1
            frame = _result(pending.popleft(), cancel)
            if frame is None:
                return False
            writer.write(frame)
            tracker.frames(written + 1)
        return True
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _result(future: Future[RGBImage], cancel: CancelToken) -> RGBImage | None:
    while not cancel.cancelled:
        try:
            return future.result(timeout=CANCEL_POLL_S)
        except FutureTimeout:
            continue
    return None


def _close(writer: VideoWriter, cancel: CancelToken) -> bool:
    """Finishes the encoder (faststart rewrites the file: seconds for a long video) while
    watching the token. False if cancelled; the caller aborts the writer."""
    errors: list[BaseException] = []

    def finish() -> None:
        try:
            writer.close()
        except BaseException as error:
            errors.append(error)

    closer = threading.Thread(target=finish, name="passimaker-export-finish", daemon=True)
    closer.start()
    while closer.is_alive():
        if cancel.cancelled:
            return False
        closer.join(CANCEL_POLL_S)
    if errors:
        raise errors[0]
    return True
