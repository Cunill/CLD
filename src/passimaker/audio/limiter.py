"""Look-ahead peak limiter whose output depends only on a fixed neighbourhood of each frame.

The gain at frame n is computed from the frames [n − before, n + after] and nothing else, so a
block read on its own (preview) is identical to the same frames inside the whole mix (export).

    required[k] = min(1, ceiling / peak[k])                     (peak over both channels)
    held[j]     = min(required[j − hold … j + lookahead − 1])
    gain[n]     = mean(held[n − lookahead + 1 … n])

Every held[j] in the mean covers frame n, so gain[n] ≤ required[n]: no sample ever exceeds the
ceiling. The gain falls in a straight line over `lookahead` frames before a peak, stays down for
`hold` frames after it and comes back up over `lookahead` frames.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def context(lookahead: int, hold: int) -> tuple[int, int]:
    """Frames needed (before, after) a block to compute its gain."""
    return hold + lookahead - 1, lookahead - 1


def sliding_min(values: NDArray[np.float64], width: int) -> NDArray[np.float64]:
    """Minimum of each window of `width` consecutive values (len − width + 1 results).

    Van Herk / Gil-Werman: running minima inside fixed blocks, in both directions; O(n).
    """
    n = len(values)
    if width <= 1:
        return values.copy()
    if n < width:
        return np.zeros(0, dtype=values.dtype)
    blocks = -(-n // width)
    padded = np.full(blocks * width, np.inf, dtype=values.dtype)
    padded[:n] = values
    shaped = padded.reshape(blocks, width)
    prefix = np.minimum.accumulate(shaped, axis=1).ravel()
    suffix = np.minimum.accumulate(shaped[:, ::-1], axis=1)[:, ::-1].ravel()
    count = n - width + 1
    return np.minimum(suffix[:count], prefix[width - 1 : width - 1 + count])


def _stereo_peak(signal: NDArray[np.float32]) -> NDArray[np.float64]:
    """Peak of each frame over both channels (much faster than a max along the short axis)."""
    return np.maximum(np.abs(signal[:, 0]), np.abs(signal[:, 1])).astype(np.float64)


def limit(signal: NDArray[np.float32], lookahead: int, hold: int, ceiling: float) -> NDArray[np.float32]:
    """Limits `signal` (frames × 2, stereo) and returns its central part.

    The first `before` and the last `after` frames (see `context`) are only context: the result
    has len(signal) − before − after frames.
    """
    before, after = context(lookahead, hold)
    count = len(signal) - before - after
    if count <= 0:
        return np.zeros((0, signal.shape[1]), dtype=np.float32)
    peak = _stereo_peak(signal)
    required = ceiling / np.maximum(peak, ceiling)  # exactly 1 below the ceiling
    held = sliding_min(required, hold + lookahead)
    sums = np.concatenate(([0.0], np.cumsum(held)))
    gain = (sums[lookahead:] - sums[:-lookahead]) / lookahead
    gain = np.minimum(gain[:count], required[before : before + count])  # rounding of the mean
    limited = signal[before : before + count] * gain.astype(np.float32)[:, None]
    # float32 rounding can leave a sample one step above the ceiling: clip to the step below it.
    top = np.float32(ceiling)
    if top > ceiling:
        top = np.nextafter(top, np.float32(0))
    return np.clip(limited, -top, top, out=limited)
