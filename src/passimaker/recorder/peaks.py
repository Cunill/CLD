"""Wave columns (minimum and maximum per channel), computed in the capture thread (pure, NumPy).

PeakBuffer turns the captured blocks into columns of `frames_per_column` frames each and keeps
either the last `capacity` columns (the live waves) or all of them (a whole recording). It is not
thread-safe by itself: Recorder and Monitor guard it with their lock.
"""

from __future__ import annotations

import numpy as np

from passimaker.recorder.types import AudioFrames, PeakColumns


def frames_per_column(sample_rate: int, columns_per_s: int) -> int:
    """Whole frames per column, so that columns line up with frames (48 kHz at 50/s: 960)."""
    if sample_rate <= 0 or columns_per_s <= 0:
        raise ValueError("sample_rate and columns_per_s must be positive")
    return max(1, round(sample_rate / columns_per_s))


class PeakBuffer:
    def __init__(self, channels: int, frames_per_column: int, capacity: int | None = None) -> None:
        """`capacity` None keeps every column; otherwise only the last `capacity`."""
        if channels <= 0 or frames_per_column <= 0 or (capacity is not None and capacity <= 0):
            raise ValueError("channels, frames_per_column and capacity must be positive")
        self.channels = channels
        self.frames_per_column = frames_per_column
        self._capacity = capacity
        self._columns: PeakColumns = np.zeros((capacity or 1024, channels, 2), dtype=np.float32)
        self._total = 0
        self._pending_min = np.zeros(channels, dtype=np.float32)
        self._pending_max = np.zeros(channels, dtype=np.float32)
        self._pending_frames = 0

    @property
    def total(self) -> int:
        """Columns completed so far (also those a ring buffer no longer keeps)."""
        return self._total

    def add(self, block: AudioFrames) -> None:
        """Frames of shape (frames, channels); an incomplete last column waits for the next block."""
        start = 0
        frames = block.shape[0]
        if self._pending_frames:
            take = min(frames, self.frames_per_column - self._pending_frames)
            if take:
                part = block[:take]
                self._pending_min = np.minimum(self._pending_min, part.min(axis=0))
                self._pending_max = np.maximum(self._pending_max, part.max(axis=0))
                self._pending_frames += take
                start = take
            if self._pending_frames < self.frames_per_column:
                return
            self._append(np.stack((self._pending_min, self._pending_max), axis=-1)[np.newaxis])
            self._pending_frames = 0
        whole = (frames - start) // self.frames_per_column
        if whole:
            end = start + whole * self.frames_per_column
            shaped = block[start:end].reshape(whole, self.frames_per_column, self.channels)
            self._append(np.stack((shaped.min(axis=1), shaped.max(axis=1)), axis=-1))
            start = end
        if start < frames:
            rest = block[start:]
            self._pending_min = rest.min(axis=0)
            self._pending_max = rest.max(axis=0)
            self._pending_frames = frames - start

    def flush(self) -> None:
        """Complete the last column with the frames it has (at the end of a recording)."""
        if self._pending_frames:
            self._append(np.stack((self._pending_min, self._pending_max), axis=-1)[np.newaxis])
            self._pending_frames = 0

    def since(self, index: int) -> tuple[PeakColumns, int]:
        """The columns after `index` (as many as are still kept) and the new index."""
        first = max(0, index, self._total - self._kept())
        return self._slice(first, self._total), self._total

    def all(self) -> PeakColumns:
        return self._slice(self._total - self._kept(), self._total)

    def _kept(self) -> int:
        return self._total if self._capacity is None else min(self._total, self._capacity)

    def _slice(self, first: int, end: int) -> PeakColumns:
        if first >= end:
            return np.zeros((0, self.channels, 2), dtype=np.float32)
        if self._capacity is None:
            return self._columns[first:end].copy()
        positions = np.arange(first, end) % self._capacity
        return self._columns[positions]

    def _append(self, columns: PeakColumns) -> None:
        count = columns.shape[0]
        if self._capacity is None:
            needed = self._total + count
            if needed > self._columns.shape[0]:
                size = max(needed, 2 * self._columns.shape[0])
                grown = np.zeros((size, self.channels, 2), dtype=np.float32)
                grown[: self._total] = self._columns[: self._total]
                self._columns = grown
            self._columns[self._total : needed] = columns
        else:
            columns = columns[-self._capacity :]
            skipped = count - columns.shape[0]
            positions = np.arange(self._total + skipped, self._total + count, dtype=np.int64) % self._capacity
            self._columns[positions] = columns
        self._total += count


def reduce_columns(columns: PeakColumns, width: int) -> PeakColumns:
    """`columns` reduced (or stretched) to exactly `width` columns, keeping each range's extremes."""
    if width <= 0:
        raise ValueError("width must be positive")
    count = columns.shape[0]
    channels = columns.shape[1]
    if count == 0:
        return np.zeros((width, channels, 2), dtype=np.float32)
    # Column i takes the input columns from starts[i] up to starts[i + 1] (the last one, to the end).
    starts = np.floor(np.arange(width) * (count / width)).astype(np.int64)
    if count < width:
        return columns[starts].copy()
    result = np.empty((width, channels, 2), dtype=np.float32)
    result[:, :, 0] = np.minimum.reduceat(columns[:, :, 0], starts, axis=0)
    result[:, :, 1] = np.maximum.reduceat(columns[:, :, 1], starts, axis=0)
    return result
