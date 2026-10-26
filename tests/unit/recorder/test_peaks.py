"""C09: wave columns (PeakBuffer) and the overview (reduce_columns), pure NumPy."""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from passimaker.recorder.peaks import PeakBuffer, frames_per_column, reduce_columns


def _expected(samples: np.ndarray, per_column: int) -> np.ndarray:
    whole = samples.shape[0] // per_column
    shaped = samples[: whole * per_column].reshape(whole, per_column, samples.shape[1])
    return np.stack((shaped.min(axis=1), shaped.max(axis=1)), axis=-1)


@given(
    samples=hnp.arrays(
        np.float32,
        st.tuples(st.integers(0, 400), st.integers(1, 2)),
        elements=st.floats(-1, 1, width=32),
    ),
    per_column=st.integers(1, 37),
    cuts=st.lists(st.integers(0, 400), max_size=6),
)
def test_columns_do_not_depend_on_how_the_blocks_are_cut(
    samples: np.ndarray, per_column: int, cuts: list[int]
) -> None:
    buffer = PeakBuffer(samples.shape[1], per_column)
    edges = sorted({0, samples.shape[0], *(c for c in cuts if c < samples.shape[0])})
    for start, end in itertools.pairwise(edges):
        buffer.add(samples[start:end])
    expected = _expected(samples, per_column)
    assert buffer.total == expected.shape[0]
    np.testing.assert_array_equal(buffer.all(), expected)
    buffer.flush()
    rest = samples.shape[0] % per_column
    assert buffer.total == expected.shape[0] + (1 if rest else 0)
    if rest:
        tail = samples[-rest:]
        np.testing.assert_array_equal(
            buffer.all()[-1], np.stack((tail.min(axis=0), tail.max(axis=0)), axis=-1)
        )


def test_a_ring_keeps_the_last_columns_and_counts_them_all() -> None:
    buffer = PeakBuffer(1, 2, capacity=3)
    buffer.add(np.arange(20, dtype=np.float32).reshape(-1, 1))  # 10 columns at once
    assert buffer.total == 10
    np.testing.assert_array_equal(buffer.all()[:, 0, 1], [15, 17, 19])
    columns, index = buffer.since(0)
    assert index == 10 and columns.shape[0] == 3
    columns, _ = buffer.since(9)
    np.testing.assert_array_equal(columns[:, 0, 0], [18])
    buffer.add(np.array([[30.0], [31.0]], dtype=np.float32))
    np.testing.assert_array_equal(buffer.since(10)[0][:, 0, 1], [31])
    assert buffer.since(11)[0].shape[0] == 0


def test_frames_per_column() -> None:
    assert frames_per_column(48000, 50) == 960
    assert frames_per_column(44100, 50) == 882
    with pytest.raises(ValueError):
        frames_per_column(0, 50)


@given(
    count=st.integers(0, 300),
    width=st.integers(1, 120),
    seed=st.integers(0, 2**32 - 1),
)
def test_the_overview_keeps_the_extremes(count: int, width: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    low = -rng.random((count, 2), dtype=np.float32)
    columns = np.stack((low, -low / 2), axis=-1).astype(np.float32)
    reduced = reduce_columns(columns, width)
    assert reduced.shape == (width, 2, 2) and reduced.dtype == np.float32
    if count:
        assert float(reduced[:, :, 0].min()) == float(columns[:, :, 0].min())
        assert float(reduced[:, :, 1].max()) == float(columns[:, :, 1].max())
    else:
        assert not reduced.any()


def test_the_overview_in_order() -> None:
    columns = np.zeros((6, 1, 2), dtype=np.float32)
    columns[:, 0, 1] = [1, 2, 3, 4, 5, 6]
    np.testing.assert_array_equal(reduce_columns(columns, 3)[:, 0, 1], [2, 4, 6])
    np.testing.assert_array_equal(reduce_columns(columns, 12)[:, 0, 1], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6])
