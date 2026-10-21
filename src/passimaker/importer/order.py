"""Import order (docs/ESPECIFICACIO.md §1.1): by capture date or by natural name."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from passimaker.importer.types import PhotoCandidate
from passimaker.model import defaults
from passimaker.model.editing import natural_key


def _name_key(candidate: PhotoCandidate) -> tuple[tuple[str | int, ...], str]:
    return natural_key(candidate.path.name), str(candidate.path).casefold()


def _date_key(candidate: PhotoCandidate) -> tuple[datetime, tuple[tuple[str | int, ...], str]]:
    when = candidate.capture_time if candidate.capture_time is not None else candidate.file_time
    return when.replace(tzinfo=None), _name_key(candidate)


def prefers_date_order(candidates: Sequence[PhotoCandidate]) -> bool:
    if not candidates:
        return False
    dated = sum(1 for c in candidates if c.capture_time is not None)
    return dated >= defaults.DATE_ORDER_MIN_FRACTION * len(candidates)


def sort_candidates(
    candidates: Sequence[PhotoCandidate], *, by_date: bool | None = None
) -> list[PhotoCandidate]:
    """by_date=None applies the automatic rule (date if >= 80 % have EXIF date, else natural name).

    By date, photos without a capture date use the file date. Ties (and the name order) use the
    file name in natural order ("IMG_2" before "IMG_10"), then the full path.
    """
    use_date = prefers_date_order(candidates) if by_date is None else by_date
    return sorted(candidates, key=_date_key if use_date else _name_key)
