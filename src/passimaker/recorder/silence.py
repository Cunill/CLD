"""Silence at the start and at the end of a recording (pure, NumPy)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from passimaker.model import defaults


def dbfs_to_amplitude(dbfs: float) -> float:
    return float(10.0 ** (dbfs / 20.0))


def amplitude_to_dbfs(amplitude: float) -> float:
    """-inf for 0 (digital silence)."""
    return 20.0 * math.log10(amplitude) if amplitude > 0 else -math.inf


def normalize_gain(peak: float, target_dbfs: float = defaults.RECORD_NORMALIZE_PEAK_DBFS) -> float:
    """The factor that raises a recording whose highest |sample| is `peak` to `target_dbfs`.

    Never below 1 (a loud recording stays as it is) and never above what brings the peak to the
    target, so the result never goes over `target_dbfs`. 1 for a silent recording (peak 0).
    """
    target = dbfs_to_amplitude(target_dbfs)
    if not peak > 0 or peak >= target:
        return 1.0
    # The samples are float32: rounding could put the peak a hair over the target, so step back.
    gain = np.float32(min(target / peak, float(np.finfo(np.float32).max)))
    while np.float32(peak) * gain > np.float32(target):
        gain = np.nextafter(gain, np.float32(0.0))
    return max(1.0, float(gain))


def trim_silence(
    samples: NDArray[np.float32],
    sample_rate: float,
    threshold_dbfs: float = defaults.RECORD_TRIM_THRESHOLD_DBFS,
    margin_s: float = defaults.RECORD_TRIM_MARGIN_S,
) -> tuple[float, float] | None:
    """`(start_s, end_s)` of the part to keep; None if every sample is below the threshold.

    `samples` has shape (frames, channels) or (frames,): the audio itself, or an envelope such as
    the maximum of the absolute peaks per wave column, with `sample_rate` the columns per second.
    A frame is sound when any channel reaches `threshold_dbfs`. `margin_s` is kept before the first
    sound and after the last one, within the recording.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if margin_s < 0:
        raise ValueError("margin_s must not be negative")
    frames = samples.shape[0]
    if frames == 0:
        return None
    magnitude = np.abs(samples) if samples.ndim == 1 else np.abs(samples).max(axis=1)
    loud = np.flatnonzero(magnitude >= dbfs_to_amplitude(threshold_dbfs))
    if loud.size == 0:
        return None
    duration_s = frames / sample_rate
    start_s = max(0.0, float(loud[0]) / sample_rate - margin_s)
    end_s = min(duration_s, float(loud[-1] + 1) / sample_rate + margin_s)
    return start_s, end_s
