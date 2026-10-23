"""B13 · The playback loop with a simulated clock and a simulated sound device.

The loop runs step by step on the test thread; waiting moves the simulated clock and drawing a
frame costs simulated time (SlowFrames), so every test is exact and takes no real time.
"""

from __future__ import annotations

import statistics

import pytest

from passimaker.model.commands import SetDefaultDuration
from passimaker.preview import (
    Delivery,
    PlaybackLoop,
    PlayState,
    Scene,
    photo_index_at,
    photo_start,
    same_place,
)
from passimaker.timeline import Timeline, compute_timeline, frame_to_time, query, time_to_frame
from tests.fakes.audio import ToneAudioSource
from tests.fakes.clock import SimulatedClock
from tests.fakes.timeline import fixed_timeline
from tests.ui.helpers import controller_with
from tests.unit.preview.fakes import FakeAudioOutput, SimulatedClockFactory, SlowFrames

FPS = 30
SIZE = (96, 54)


def timeline_of(count: int = 20, duration_s: float = 5.0) -> Timeline:
    return fixed_timeline([f"p{i:04d}" for i in range(count)], duration_s=duration_s, crossfade_s=1.0)


class Harness:
    """A loop with a simulated sound device; `wait` moves the clock instead of sleeping."""

    def __init__(
        self,
        timeline: Timeline | None = None,
        costs_s: tuple[float, ...] = (0.005,),
        *,
        music: bool = True,
        fail_output: bool = False,
    ) -> None:
        self.clock = SimulatedClock()
        self.timeline = timeline if timeline is not None else timeline_of()
        self.output = FakeAudioOutput(self.clock, fail=fail_output)
        self.internal = SimulatedClockFactory(self.clock)
        self.frames = SlowFrames(self.clock, costs_s)
        self.audio = ToneAudioSource(self.timeline.total_duration_s) if music else None
        self.deliveries: list[Delivery] = []
        self.states: list[PlayState] = []
        self.idle = False
        self.loop = PlaybackLoop(
            Scene(self.frames, self.timeline, self.audio),
            self.output,
            self.deliveries.append,
            self.states.append,
            clock_factory=self.internal,
            size=SIZE,
        )

    def wait(self, timeout_s: float | None) -> None:
        if timeout_s is None:
            self.idle = True
        else:
            self.clock.advance(timeout_s)

    def settle(self, max_steps: int = 100) -> None:
        """Steps until the loop has nothing left to do (paused)."""
        self.idle = False
        for _ in range(max_steps):
            self.loop.step(self.wait)
            if self.idle:
                return
        raise AssertionError("el bucle no s'atura")

    def run_for(self, seconds: float) -> None:
        """Steps while playing until `seconds` of show time have passed (or the show ends)."""
        end = self.clock.now() + seconds
        self.loop.step(self.wait)  # applies a pending play
        while self.clock.now() < end and self.loop.state.playing:
            self.loop.step(self.wait)

    def played(self) -> list[Delivery]:
        return [d for d in self.deliveries if d.clock_s is not None]


def lag_frames(delivery: Delivery) -> float:
    """Distance, in frames, between the instant of the image and the clock when it is ready."""
    assert delivery.clock_s is not None
    return abs(delivery.clock_s - delivery.t) * FPS


def assert_in_sync(deliveries: list[Delivery], *, repeats: bool = False) -> None:
    """Criterion of the plan: at most 1 frame of difference on average and 3 at most.

    Frames always go forwards; the same frame is drawn twice only after a new scene (`repeats`).
    """
    lags = [lag_frames(d) for d in deliveries]
    assert statistics.mean(lags) <= 1.0, f"mitjana {statistics.mean(lags):.2f}"
    assert max(lags) <= 3, f"màxim {max(lags)}"
    frames = [time_to_frame(d.t, FPS) for d in deliveries]
    assert frames == (sorted(frames) if repeats else sorted(set(frames))), "les imatges van enrere"


# --- Starting and drawing ------------------------------------------------------------------------


def test_starts_paused_and_draws_the_first_frame() -> None:
    harness = Harness()
    harness.settle()
    assert [d.t for d in harness.deliveries] == [0.0]
    assert harness.deliveries[0].clock_s is None
    assert harness.deliveries[0].image.shape == (SIZE[1], SIZE[0], 3)
    assert harness.output.starts == []
    assert not harness.loop.state.playing


def test_frames_have_the_size_asked_for() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.set_size(160, 90)
    harness.settle()
    assert harness.frames.sizes[-1] == (160, 90)
    assert harness.deliveries[-1].image.shape == (90, 160, 3)


# --- Synchronisation (acceptance criterion) ------------------------------------------------------


def test_playing_follows_the_sound_clock() -> None:
    harness = Harness(costs_s=(0.005,))
    harness.settle()
    harness.loop.play()
    harness.run_for(30.0)
    played = harness.played()
    assert_in_sync(played)
    # With a fast compositor almost every frame is drawn.
    assert len(played) >= 0.95 * 30.0 * FPS
    # The sound is started once and never cut while playing.
    assert harness.output.starts == [0.0]
    assert harness.output.stops == 0


@pytest.mark.parametrize(
    "costs_s",
    [
        (0.050,),
        (0.100,),
        (0.040, 0.090, 0.060, 0.110, 0.050, 0.070),
        # An unforeseen peak arrives late by its excess over the estimate: 110 ms is ~3 frames.
        (0.020, 0.020, 0.020, 0.110, 0.020, 0.020),
    ],
    ids=["50ms", "100ms", "variable", "pics"],
)
def test_a_slow_compositor_skips_frames_and_never_falls_behind(costs_s: tuple[float, ...]) -> None:
    harness = Harness(costs_s=costs_s)
    harness.settle()
    harness.loop.play()
    harness.run_for(60.0)
    played = harness.played()
    assert_in_sync(played)
    # Frames are skipped: fewer than the show has, but at least one per (slowest) drawing time.
    assert 60.0 / max(costs_s) <= len(played) < 60.0 * FPS * 0.9
    # Never behind: the last frames are as close to the clock as the first ones.
    assert max(lag_frames(d) for d in played[-20:]) <= 3
    assert harness.output.starts == [0.0]


def test_without_music_the_internal_clock_keeps_the_time() -> None:
    harness = Harness(music=False)
    harness.settle()
    harness.loop.play()
    harness.run_for(10.0)
    assert harness.output.starts == []
    assert harness.internal.starts == [0.0]
    assert_in_sync(harness.played())


def test_if_the_sound_device_fails_the_internal_clock_takes_over() -> None:
    harness = Harness(fail_output=True)
    harness.settle()
    harness.loop.play()
    harness.run_for(5.0)
    assert harness.internal.starts == [0.0]
    assert harness.loop.state.playing
    assert_in_sync(harness.played())


# --- Commands ------------------------------------------------------------------------------------


def test_pause_stops_the_sound_and_draws_the_exact_frame() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.play()
    harness.run_for(2.0)
    harness.loop.pause()
    harness.settle()
    assert harness.output.stops == 1
    state = harness.loop.state
    assert not state.playing
    last = harness.deliveries[-1]
    assert last.clock_s is None
    assert last.t == frame_to_time(time_to_frame(last.t, FPS), FPS)
    assert last.t == pytest.approx(harness.clock.now(), abs=1 / FPS)
    # Playing again starts the sound where it was paused.
    harness.loop.play()
    harness.run_for(0.5)
    assert harness.output.starts[-1] == pytest.approx(harness.played()[-1].t, abs=1.0)
    assert harness.output.starts[-1] >= 2.0


def test_seeking_while_playing_restarts_the_sound_there() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.play()
    harness.run_for(1.0)
    harness.loop.seek(42.0)
    harness.run_for(1.0)
    assert harness.output.starts == [0.0, 42.0]
    after = [d for d in harness.played() if d.t >= 42.0]
    assert after and after[0].t == pytest.approx(42.0, abs=2 / FPS)
    assert harness.loop.state.playing
    assert_in_sync(after)


def test_seeking_in_pause_draws_that_instant() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.seek(12.34)
    harness.settle()
    assert harness.deliveries[-1].t == frame_to_time(time_to_frame(12.34, FPS), FPS)
    assert harness.output.starts == []
    assert harness.states[-1] == PlayState(False, 12.34, 2)


def test_seek_photo_lands_where_the_photo_is_fully_visible() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.seek_photo(3)
    harness.settle()
    expected = photo_start(harness.timeline, 3)
    slot = harness.timeline.slots[3]
    assert slot.fade_in is not None
    assert expected == slot.fade_in.end
    assert harness.states[-1].photo_index == 3
    assert harness.deliveries[-1].t == pytest.approx(expected, abs=1 / FPS)


def test_seek_photo_while_playing_goes_on_from_there() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.play()
    harness.run_for(1.0)
    harness.loop.seek_photo(10)
    harness.run_for(1.0)
    assert harness.output.starts[-1] == photo_start(harness.timeline, 10)
    assert harness.loop.state.playing
    assert harness.loop.state.photo_index == 10


def test_refresh_in_pause_draws_again() -> None:
    harness = Harness()
    harness.settle()
    before = len(harness.deliveries)
    harness.loop.refresh()
    harness.settle()
    assert len(harness.deliveries) == before + 1


def test_a_new_scene_in_pause_is_drawn_at_once() -> None:
    harness = Harness()
    harness.loop.seek(7.0)
    harness.settle()
    longer = timeline_of(duration_s=6.0)
    other = SlowFrames(harness.clock)
    harness.loop.set_scene(Scene(other, longer, harness.audio))
    harness.settle()
    assert other.times == [frame_to_time(time_to_frame(7.0, FPS), FPS)]
    assert harness.output.starts == []


def test_a_new_scene_while_playing_keeps_the_sound_if_the_music_is_the_same() -> None:
    harness = Harness()
    harness.settle()
    harness.loop.play()
    harness.run_for(2.0)
    harness.loop.set_scene(Scene(harness.frames, timeline_of(duration_s=6.0), harness.audio))
    harness.run_for(1.0)
    assert harness.output.starts == [0.0]
    assert harness.output.stops == 0
    # New music: the sound restarts at the current position.
    harness.loop.set_scene(Scene(harness.frames, harness.timeline, ToneAudioSource(100.0, 330.0)))
    harness.run_for(1.0)
    assert len(harness.output.starts) == 2
    assert harness.output.starts[1] == pytest.approx(3.0, abs=0.2)
    assert_in_sync(harness.played(), repeats=True)


def test_the_end_of_the_show_pauses_on_the_last_frame() -> None:
    timeline = timeline_of(count=3, duration_s=2.0)
    harness = Harness(timeline)
    harness.settle()
    harness.loop.play()
    harness.run_for(20.0)
    state = harness.loop.state
    assert not state.playing
    assert not harness.loop.playing
    assert harness.played()[-1].t == frame_to_time(timeline.total_frames - 1, FPS)
    assert harness.output.stops == 1
    # Playing at the end starts again from the beginning.
    harness.loop.play()
    harness.run_for(0.5)
    assert harness.output.starts[-1] == 0.0


def test_an_empty_show_does_not_play() -> None:
    harness = Harness(fixed_timeline([]), music=False)
    harness.settle()
    harness.loop.play()
    harness.settle()
    assert not harness.loop.playing
    assert harness.internal.starts == []


def test_state_changes_are_reported_when_the_photo_changes() -> None:
    harness = Harness(timeline_of(count=4, duration_s=2.0))
    harness.settle()
    harness.loop.play()
    harness.run_for(20.0)
    indices = [s.photo_index for s in harness.states if s.playing]
    assert indices == [0, 1, 2, 3]
    assert harness.states[-1].playing is False


def test_frames_of_an_older_generation_are_marked_stale() -> None:
    harness = Harness()
    harness.settle()
    first = harness.deliveries[-1].generation
    harness.loop.seek(3.0)
    assert harness.loop.generation > first
    harness.settle()
    assert harness.deliveries[-1].generation == harness.loop.generation


# --- Scene helpers -------------------------------------------------------------------------------


def test_photo_start_skips_the_fade_from_black() -> None:
    timeline = timeline_of()
    assert timeline.fade_from_black is not None
    assert photo_start(timeline, 0) == timeline.fade_from_black.end
    assert photo_start(timeline, 99) == photo_start(timeline, 19)
    assert photo_start(fixed_timeline([]), 0) == 0.0


def test_photo_index_at() -> None:
    timeline = timeline_of(count=3, duration_s=2.0)
    assert [photo_index_at(timeline, t) for t in (0.0, 1.99, 2.0, 5.9, 6.0, 100.0)] == [0, 0, 1, 2, 2, 2]
    assert photo_index_at(fixed_timeline([]), 1.0) == -1


def test_same_place_keeps_the_photo_after_a_change_of_duration() -> None:
    old, new = timeline_of(duration_s=5.0), timeline_of(duration_s=2.0)
    # At the start of photo 3, even rounded to a frame (as the paused position is): the start.
    start = photo_start(old, 3)
    assert same_place(old, new, start) == photo_start(new, 3)
    rounded = frame_to_time(time_to_frame(start, FPS) + 1, FPS) - 1e-6
    assert same_place(old, new, rounded) == photo_start(new, 3)
    # Elsewhere, the same fraction of the photo's own space.
    middle = (old.slots[3].slot_start + old.slots[3].slot_end) / 2
    assert same_place(old, new, middle) == pytest.approx(
        (new.slots[3].slot_start + new.slots[3].slot_end) / 2
    )
    # A photo that is gone: no place.
    assert same_place(old, timeline_of(count=2), middle) is None


@pytest.mark.parametrize("duration_s", [1.0, 1.5, 2.0, 2.3, 3.0])
def test_photo_start_is_a_frame_that_shows_only_that_photo(duration_s: float) -> None:
    """Short photos get a shortened crossfade that does not end on a frame (1.5 s: 0.733 s)."""
    controller = controller_with(8)
    controller.execute(SetDefaultDuration(duration_s))
    timeline = compute_timeline(controller.project)
    for index, slot in enumerate(timeline.slots):
        t = photo_start(timeline, index)
        assert t == frame_to_time(time_to_frame(t, FPS), FPS)
        visibles = query(timeline, t)
        # Only that photo is drawn (the black fades of the start and end may still darken it).
        assert [layer.photo_id for layer in visibles.layers] == [slot.photo_id]
