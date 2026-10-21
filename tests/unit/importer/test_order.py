"""B4: sort_candidates (docs/ESPECIFICACIO.md §1.1)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from passimaker.importer import PhotoCandidate, sort_candidates
from passimaker.model import defaults

BASE = datetime(2024, 1, 1)


def _candidate(name: str, capture_day: int | None, file_day: int = 0) -> PhotoCandidate:
    capture = None if capture_day is None else BASE + timedelta(days=capture_day)
    return PhotoCandidate(Path("fotos") / name, 400, 300, 1, capture, BASE + timedelta(days=file_day), None)


def test_threshold_is_80_percent() -> None:
    assert defaults.DATE_ORDER_MIN_FRACTION == 0.8


def test_explicit_order_overrides_the_rule() -> None:
    items = [_candidate("b10.jpg", 1), _candidate("b2.jpg", 2), _candidate("a.jpg", None, 3)]
    assert [c.path.name for c in sort_candidates(items, by_date=False)] == ["a.jpg", "b2.jpg", "b10.jpg"]
    assert [c.path.name for c in sort_candidates(items, by_date=True)] == ["b10.jpg", "b2.jpg", "a.jpg"]
    assert [c.path.name for c in sort_candidates(items)] == ["a.jpg", "b2.jpg", "b10.jpg"]  # 67 %


def test_same_name_in_two_folders_is_stable() -> None:
    a = PhotoCandidate(Path("2023/IMG_1.jpg"), 400, 300, 1, None, BASE, None)
    b = PhotoCandidate(Path("2024/IMG_1.jpg"), 400, 300, 1, None, BASE, None)
    assert sort_candidates([b, a]) == [a, b]


def test_timezone_aware_dates_do_not_break_sorting() -> None:
    from datetime import UTC

    aware = PhotoCandidate(Path("x.jpg"), 400, 300, 1, datetime(2024, 1, 2, tzinfo=UTC), BASE, None)
    naive = _candidate("y.jpg", 0)
    assert [c.path.name for c in sort_candidates([aware, naive], by_date=True)] == ["y.jpg", "x.jpg"]


@given(st.lists(st.tuples(st.integers(0, 50), st.one_of(st.none(), st.integers(0, 30))), max_size=40))
def test_sorting_is_a_deterministic_permutation(specs: list[tuple[int, int | None]]) -> None:
    items = [_candidate(f"IMG_{n}_{i}.jpg", day) for i, (n, day) in enumerate(specs)]
    first = sort_candidates(items)
    assert sorted(first, key=lambda c: c.path.name) == sorted(items, key=lambda c: c.path.name)
    assert sort_candidates(list(reversed(items))) == first
    dated = sum(day is not None for _, day in specs)
    if items and dated >= 0.8 * len(items):
        keys = [c.capture_time or c.file_time for c in first]
        assert keys == sorted(keys)
