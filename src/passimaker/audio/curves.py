"""Fade curves.

Song fades and the final fade are logarithmic (§1.7): linear in dB from FADE_FLOOR_DB to 0 dB,
anchored to silence at the start. The 10 ms anti-click fades of every cut are raised cosines:
a logarithmic curve that short ends with a sudden change of slope, which is itself a small click.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from passimaker.audio.params import ANTI_CLICK_MAX_FRAMES, FADE_FLOOR_DB

_FLOOR_GAIN = 10.0 ** (FADE_FLOOR_DB / 20.0)


def fade_in_gain(progress: NDArray[np.float64]) -> NDArray[np.float64]:
    """Gain of a fade-in at `progress` (0 = start, 1 = end): 0 at 0, 1 at 1, strictly increasing.

    10^(floor·(1−p)/20) is a straight line in dB; subtracting its value at p = 0 and rescaling
    brings the start down to exact silence; above −30 dB the curve stays within 0.3 dB of the line.
    """
    p = np.clip(progress, 0.0, 1.0)
    return (np.power(10.0, FADE_FLOOR_DB * (1.0 - p) / 20.0) - _FLOOR_GAIN) / (1.0 - _FLOOR_GAIN)


def anti_click_gain(progress: NDArray[np.float64]) -> NDArray[np.float64]:
    """Raised cosine: 0 at 0, 1 at 1, with zero slope at both ends."""
    p = np.clip(progress, 0.0, 1.0)
    return np.sin(0.5 * np.pi * p) ** 2


def _curve(frames: int) -> Callable[[NDArray[np.float64]], NDArray[np.float64]]:
    return anti_click_gain if frames <= ANTI_CLICK_MAX_FRAMES else fade_in_gain


def segment_envelope(
    first: int, count: int, start: int, end: int, fade_in: int, fade_out: int
) -> NDArray[np.float64]:
    """Gain of the frames [first, first + count) of a segment that plays over [start, end).

    The fade-in rises over [start, start + fade_in) and the fade-out falls over [end − fade_out, end):
    the first frame of a segment and the frame right after it are silent. Fades of up to
    ANTI_CLICK_MAX_FRAMES are anti-click fades (raised cosine); longer ones are logarithmic.
    """
    gain = np.ones(count, dtype=np.float64)
    if fade_in > 0 and first < start + fade_in:  # only the frames inside a fade are computed
        part = slice(0, min(count, start + fade_in - first))
        n = np.arange(first, first + part.stop, dtype=np.float64)
        gain[part] *= _curve(fade_in)((n - start) / fade_in)
    if fade_out > 0 and first + count > end - fade_out:
        part = slice(max(0, end - fade_out - first), count)
        n = np.arange(first + part.start, first + count, dtype=np.float64)
        gain[part] *= _curve(fade_out)((end - n) / fade_out)
    return gain


def fade_out_envelope(first: int, count: int, start: int, end: int) -> NDArray[np.float64]:
    """Gain of the frames [first, first + count) for a fade-out over [start, end); 0 from `end` on."""
    n = np.arange(first, first + count, dtype=np.float64)
    gain = np.ones(count, dtype=np.float64)
    length = end - start
    if length > 0:
        gain = fade_in_gain((end - n) / length)
    gain[n >= end] = 0.0
    return gain
