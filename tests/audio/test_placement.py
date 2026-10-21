"""Songs one after another, where the plan says (±10 ms by dominant frequency), with their trims."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from passimaker.timeline import compute_timeline
from tests.audio.conftest import SR, Mixer, dominant, level, project, song

CHUNK = 240  # 5 ms
TOLERANCE_S = 0.010


def spans(labels: list[float | None]) -> dict[float, tuple[float, float]]:
    """First and last instant of each frequency, in seconds."""
    result: dict[float, tuple[float, float]] = {}
    for i, label in enumerate(labels):
        if label is None:
            continue
        start, _ = result.get(label, (i * CHUNK / SR, 0.0))
        result[label] = (start, (i + 1) * CHUNK / SR)
    return result


def test_each_song_starts_and_ends_where_the_plan_says(songs: dict[str, Path], mixer: Mixer) -> None:
    p = project(
        8.0,
        [
            song(songs, "440", trim=(1.0, 3.5)),
            song(songs, "660", trim=(0.0, 2.0)),
            song(songs, "880", trim=(4.0, 6.5)),
        ],
    )
    plan = compute_timeline(p).audio_plan
    out = mixer(p).read(0.0, 8 * SR)
    found = spans(dominant(out, CHUNK, (440.0, 660.0, 880.0)))
    for segment, frequency in zip(plan.segments, (440.0, 660.0, 880.0), strict=True):
        start, end = found[frequency]
        assert abs(start - segment.video_start) <= TOLERANCE_S
        assert abs(end - segment.video_end) <= TOLERANCE_S
    assert [s.video_end for s in plan.segments] == [2.5, 4.5, 7.0]
    assert np.all(out[7 * SR :] == 0)


def test_the_trim_start_picks_the_right_part_of_the_file(songs: dict[str, Path], mixer: Mixer) -> None:
    """The step song is 440 Hz for 2 s and then 660 Hz: trimmed from 1.5 s, it changes at 0.5 s."""
    out = mixer(project(4.0, [song(songs, "step", trim=(1.5, 3.0))])).read(0.0, 2 * SR)
    found = spans(dominant(out, CHUNK, (440.0, 660.0)))
    assert abs(found[440.0][1] - 0.5) <= TOLERANCE_S
    assert abs(found[660.0][0] - 0.5) <= TOLERANCE_S
    assert abs(found[660.0][1] - 1.5) <= TOLERANCE_S


def test_compressed_song_plays_at_the_right_time(songs: dict[str, Path], mixer: Mixer) -> None:
    out = mixer(project(10.0, [song(songs, "mp3", trim=(2.0, 5.0))])).read(0.0, 4 * SR)
    found = spans(dominant(out, CHUNK, (440.0,)))
    assert abs(found[440.0][0]) <= TOLERANCE_S
    assert abs(found[440.0][1] - 3.0) <= TOLERANCE_S


def test_mono_at_44_1_khz_plays_on_both_sides_at_48_khz(songs: dict[str, Path], mixer: Mixer) -> None:
    out = mixer(project(4.0, [song(songs, "mono_44k")], normalize=False)).read(0.0, 3 * SR)
    np.testing.assert_array_equal(out[:, 0], out[:, 1])
    assert abs(level(out, 880, SR, SR) - 0.25) < 0.002
    assert level(out, 875, SR, SR) < 0.1 * level(out, 880, SR, SR)
