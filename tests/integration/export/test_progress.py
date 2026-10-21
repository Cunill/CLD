"""B9: progress tracker, keeping the computer awake and cache location (no FFmpeg)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from passimaker.export import CACHE_ENV_VAR, audio_cache_dir, cache_root, power
from passimaker.export.files import long_path, remove_quietly
from passimaker.export.params import AUDIO_SHARE, ETA_MIN_FRAMES, FINISH_SHARE, PROGRESS_INTERVAL_S
from passimaker.export.progress import ProgressTracker
from tests.integration.export.conftest import ProgressLog


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_progress_is_monotonic_and_covers_every_phase() -> None:
    clock, log = FakeClock(), ProgressLog()
    tracker = ProgressTracker(log, 300, clock=clock)
    tracker.start()
    for done in range(0, 11):
        clock.now += 0.2
        tracker.audio(done, 10)
    assert log.calls[-1][0] == pytest.approx(AUDIO_SHARE)
    for written in range(1, 301):
        clock.now += 0.04
        tracker.frames(written)
    assert log.calls[-1][0] == pytest.approx(1.0 - FINISH_SHARE, abs=0.01)
    clock.now += 1.0
    tracker.audio(5, 10)  # late or repeated reports never move the bar back
    tracker.finished()
    fractions = [f for f, _ in log.calls]
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert fractions == sorted(fractions)


def test_remaining_time_follows_the_frame_rate() -> None:
    clock, log = FakeClock(), ProgressLog()
    tracker = ProgressTracker(log, 1000, clock=clock)
    tracker.start()
    for written in range(1, 501):
        clock.now += 0.05  # 20 frames per second
        tracker.frames(written)
    assert all(r is None for f, r in log.calls if f < AUDIO_SHARE)
    _, remaining = log.calls[-1]
    assert remaining is not None
    # 500 frames left at 20 per second, plus the closing share.
    assert remaining == pytest.approx(25.0, rel=0.05)
    assert all(r is not None for _, r in log.calls[ETA_MIN_FRAMES // 2 + 1 :])
    tracker.finished()
    assert log.calls[-1] == (1.0, 0.0)


def test_progress_calls_are_throttled() -> None:
    clock, log = FakeClock(), ProgressLog()
    tracker = ProgressTracker(log, 10_000, clock=clock)
    tracker.start()
    for written in range(1, 1001):
        clock.now += 0.001
        tracker.frames(written)
    tracker.finished()
    # 1 s of frames: about one call per interval, plus the first and the last.
    assert len(log.calls) <= 1.0 / PROGRESS_INTERVAL_S + 3


def test_no_callback_is_fine() -> None:
    tracker = ProgressTracker(None, 10)
    tracker.start()
    tracker.frames(10)
    tracker.finished()
    assert tracker.fraction == 1.0


def test_keep_awake_sets_and_clears_the_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(power, "set_execution_state", lambda flags: calls.append(flags) or True)
    with pytest.raises(RuntimeError), power.keep_awake():
        assert calls == [power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED]
        raise RuntimeError
    assert calls[-1] == power.ES_CONTINUOUS


@pytest.mark.skipif(sys.platform != "win32", reason="SetThreadExecutionState només existeix a Windows")
def test_windows_accepts_the_execution_state() -> None:
    assert power.set_execution_state(power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED)
    assert power.set_execution_state(power.ES_CONTINUOUS)


def test_cache_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(CACHE_ENV_VAR, str(tmp_path))
    assert cache_root() == tmp_path
    assert audio_cache_dir() == tmp_path / "audio"
    monkeypatch.delenv(CACHE_ENV_VAR)
    root = cache_root()
    assert root.name in ("cache", "passimaker")
    if sys.platform == "win32":
        assert root.parent.name == "PassiMaker"


def test_long_windows_paths_get_the_extended_prefix() -> None:
    deep = Path("C:/" + "carpeta amb accents àèí/" * 12 + "vídeo.mp4")
    if sys.platform == "win32":
        assert str(long_path(deep, "win32")).startswith("\\\\?\\C:\\")
        unc = Path("\\\\servidor\\comparticio\\" + "x" * 250 + "\\v.mp4")
        assert str(long_path(unc, "win32")).startswith("\\\\?\\UNC\\servidor\\")
    short = Path("curt.mp4").absolute()
    assert long_path(short, "win32") == short
    assert long_path(deep, "linux") == deep.absolute()


def test_removing_a_leftover_never_raises(tmp_path: Path) -> None:
    leftover = tmp_path / "v.mp4.part"
    leftover.write_bytes(b"x")
    remove_quietly(leftover)
    remove_quietly(leftover)  # already gone
    remove_quietly(tmp_path)  # a folder: left alone, no error
    assert not leftover.exists() and tmp_path.is_dir()
