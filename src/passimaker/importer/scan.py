"""Finding photos in files and folders and reading their headers (never their pixels)."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

from passimaker.common import CancelToken, ProgressCallback
from passimaker.images.decode import (
    REASON_NOT_FOUND,
    REASON_OUT_OF_MEMORY,
    REASON_TOO_LARGE,
    REASON_UNSUPPORTED,
    ImageReadError,
    read_header,
)
from passimaker.importer.order import sort_candidates
from passimaker.importer.types import (
    RAW_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    FailedFile,
    ImportFailure,
    ImportResult,
    PhotoCandidate,
)
from passimaker.model import defaults

READ_WORKERS = 4
"""Headers are read in parallel: on network drives and OneDrive the time is spent waiting."""

_REASONS: dict[str, ImportFailure] = {
    REASON_NOT_FOUND: ImportFailure.NOT_FOUND,
    REASON_UNSUPPORTED: ImportFailure.UNSUPPORTED,
    REASON_TOO_LARGE: ImportFailure.UNSUPPORTED,
    REASON_OUT_OF_MEMORY: ImportFailure.UNSUPPORTED,
}


def path_key(path: Path) -> str:
    """Comparable form of a path: absolute, normalised and, on Windows, case-insensitive."""
    return os.path.normcase(os.path.abspath(path))  # noqa: PTH100 (no disk access, unlike resolve)


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def _classify(path: Path) -> ImportFailure | None:
    """None for a supported photo extension, else why it is not imported."""
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return None
    if suffix in RAW_EXTENSIONS:
        return ImportFailure.RAW
    return ImportFailure.UNSUPPORTED


def _walk(folder: Path, recursive: bool) -> tuple[list[Path], list[FailedFile], int]:
    """Photos in `folder` (sorted by name), RAW files found, and photos left in subfolders.

    Inside folders, files that are not photos (documents, music, videos...) are skipped silently;
    RAW files are reported so that the user knows why they are missing.
    """
    photos: list[Path] = []
    failures: list[FailedFile] = []
    in_subfolders = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not _is_hidden(d))
        top = Path(root) == folder
        for name in sorted(files):
            if _is_hidden(name):
                continue
            path = Path(root) / name
            reason = _classify(path)
            if not top and not recursive:
                in_subfolders += reason is None
            elif reason is None:
                photos.append(path)
            elif reason is ImportFailure.RAW:
                failures.append(FailedFile(path, reason))
    return photos, failures, in_subfolders


def collect_files(
    paths: Iterable[Path], *, include_subfolders: bool
) -> tuple[list[Path], list[FailedFile], int]:
    """Expands folders into photo files, in the order given. Returns files, failures and the
    number of photos in subfolders that were not included."""
    files: list[Path] = []
    failures: list[FailedFile] = []
    in_subfolders = 0
    for path in paths:
        if path.is_dir():
            found, failed, skipped = _walk(path, include_subfolders)
            files += found
            failures += failed
            in_subfolders += skipped
        elif not path.exists():
            failures.append(FailedFile(path, ImportFailure.NOT_FOUND))
        else:
            reason = _classify(path)
            if reason is None:
                files.append(path)
            else:
                failures.append(FailedFile(path, reason))
    return files, failures, in_subfolders


def read_candidate(path: Path) -> PhotoCandidate | FailedFile:
    """Reads the header of one file. Never raises: problems become a FailedFile."""
    try:
        file_time = datetime.fromtimestamp(path.stat().st_mtime)
        header = read_header(path)
    except ImageReadError as exc:
        return FailedFile(path, _REASONS.get(exc.reason, ImportFailure.CORRUPT))
    except (FileNotFoundError, NotADirectoryError):
        return FailedFile(path, ImportFailure.NOT_FOUND)
    except Exception:  # permissions, network errors, odd timestamps...
        return FailedFile(path, ImportFailure.CORRUPT)
    width, height = header.oriented_size
    if min(width, height) < defaults.MIN_PHOTO_SIDE_PX:
        return FailedFile(path, ImportFailure.TOO_SMALL)
    return PhotoCandidate(
        path=path,
        width=width,
        height=height,
        exif_orientation=header.orientation,
        capture_time=header.capture_time,
        file_time=file_time,
        color_profile=header.color_profile,
    )


def import_paths(
    paths: Sequence[Path],
    *,
    existing: frozenset[Path] = frozenset(),
    include_subfolders: bool = False,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> ImportResult:
    """Scans files and folders, reads headers (not full images), validates and sorts.

    - A file given twice (directly or through its folder) is read once.
    - Files already in `existing` are returned as duplicates and not read.
    - progress(done, total) counts the files whose header has been read (from the calling thread).
    - When cancelled, the photos read so far are returned (sorted) with cancelled=True.
    - Pixel data is not decoded here: a file whose header is fine but whose image data is
      damaged is detected later, by passimaker.images (ImageDecodeError "images.corrupt").
    """
    files, failures, in_subfolders = collect_files(paths, include_subfolders=include_subfolders)
    existing_keys = {path_key(p) for p in existing}
    seen: set[str] = set()
    duplicates: list[Path] = []
    to_read: list[Path] = []
    for path in files:
        key = path_key(path)
        if key in seen:
            continue
        seen.add(key)
        if key in existing_keys:
            duplicates.append(path)
        else:
            to_read.append(path)

    total = len(to_read)
    results: dict[int, PhotoCandidate | FailedFile] = {}
    cancelled = False
    if progress is not None:
        progress(0, total)
    if to_read:
        with ThreadPoolExecutor(max_workers=READ_WORKERS, thread_name_prefix="passimaker-import") as pool:
            pending: dict[Future[PhotoCandidate | FailedFile], int] = {}
            next_index = 0
            while next_index < total or pending:
                if cancel is not None and cancel.cancelled:
                    cancelled = True
                    break
                # Keep the queue short so that cancelling does not wait for queued files.
                while next_index < total and len(pending) < 2 * READ_WORKERS:
                    pending[pool.submit(read_candidate, to_read[next_index])] = next_index
                    next_index += 1
                done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in done:
                    results[pending.pop(future)] = future.result()
                    if progress is not None:
                        progress(len(results), total)
            for future in pending:
                future.cancel()

    candidates: list[PhotoCandidate] = []
    for index in sorted(results):
        item = results[index]
        if isinstance(item, PhotoCandidate):
            candidates.append(item)
        else:
            failures.append(item)
    return ImportResult(
        candidates=tuple(sort_candidates(candidates)),
        failures=tuple(failures),
        duplicates=tuple(duplicates),
        subfolder_photo_count=in_subfolders,
        cancelled=cancelled and len(results) < total,
    )
