"""The playback loop: what the render thread does, without Qt and without its own thread.

Every command (play, pause, seek, a new scene...) only records a request and wakes the loop; the
loop applies the requests, starts and stops the sound and draws the frames, all on the render
thread. So the interface thread never waits for the compositor or for the sound card (rule 6),
and the tests can run the very same loop step by step with a simulated clock.

While playing, the clock decides everything: the sound output's clock when there is music, an
internal one otherwise. The loop never sends the clock a frame: it asks the clock where the show
is and draws the frame that will be on screen when the drawing is done (passimaker.preview.scheduler).
"""

from __future__ import annotations

import bisect
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from passimaker.audio import AudioSource
from passimaker.common import RGBImage
from passimaker.preview.clock import ClockFactory, MonotonicClock
from passimaker.preview.params import MAX_WAIT_S, PREVIEW_MAX_SIZE
from passimaker.preview.scheduler import FrameScheduler
from passimaker.preview.types import AudioOutput, Clock, FrameSource
from passimaker.timeline import Timeline, frame_to_time, time_to_frame

_log = logging.getLogger(__name__)

_MIN_WAIT_S = 0.001
"""Shortest wait while playing (never a busy loop)."""
_EARLY_TOLERANCE_S = 0.25 / 30
"""A frame ready more than a quarter of a frame before its instant is held until then."""


@dataclass(frozen=True, slots=True)
class Scene:
    """What is played: the frames, their timeline and the sound (None: no music)."""

    frames: FrameSource
    timeline: Timeline
    audio: AudioSource | None


@dataclass(frozen=True, slots=True)
class Delivery:
    """A frame drawn by the loop. `clock_s` is the clock when it was ready (None in pause)."""

    image: RGBImage
    t: float
    generation: int
    clock_s: float | None


@dataclass(frozen=True, slots=True)
class PlayState:
    playing: bool
    t: float
    photo_index: int


type Waiter = Callable[[float | None], None]
"""Waits up to the given seconds (None: until a command arrives)."""


def photo_index_at(timeline: Timeline, t: float) -> int:
    """Index of the photo whose own space contains t (-1 if the show has no photos)."""
    if not timeline.slots:
        return -1
    starts = [slot.slot_start for slot in timeline.slots]
    return max(0, min(len(starts) - 1, bisect.bisect_right(starts, t) - 1))


def photo_start(timeline: Timeline, index: int) -> float:
    """Where "go to photo `index`" lands: the first instant the photo is fully visible.

    That is the end of its crossfade (or of the fade from black, for the first photo), so a
    still preview shows the photo itself and not a mix with the previous one or a black frame.
    """
    if not timeline.slots:
        return 0.0
    slot = timeline.slots[max(0, min(len(timeline.slots) - 1, index))]
    start = slot.slot_start if slot.fade_in is None else slot.fade_in.end
    black = timeline.fade_from_black
    if black is not None and black.end < slot.slot_end:
        start = max(start, black.end)
    return min(max(start, slot.slot_start), slot.slot_end)


def same_place(old: Timeline, new: Timeline, t: float) -> float | None:
    """Where instant t of `old` is in `new`: the same photo, at the same fraction of its space.

    After an edit in pause the preview stays on the photo it was showing even if the photos
    before it changed length. None if that photo is no longer in the show.
    """
    index = photo_index_at(old, t)
    if index < 0:
        return None
    photo_id = old.slots[index].photo_id
    target = next((slot for slot in new.slots if slot.photo_id == photo_id), None)
    if target is None:
        return None
    if abs(t - photo_start(old, index)) < 1e-9:
        return photo_start(new, target.index)
    slot = old.slots[index]
    fraction = (t - slot.slot_start) / max(1e-9, slot.slot_end - slot.slot_start)
    return target.slot_start + min(1.0, max(0.0, fraction)) * (target.slot_end - target.slot_start)


@dataclass(slots=True)
class _Requests:
    scene: Scene | None = None
    scene_at: float | None = None
    size: tuple[int, int] | None = None
    seek: float | None = None
    seek_photo: int | None = None
    redraw: bool = False

    def __bool__(self) -> bool:
        return (
            self.scene is not None
            or self.size is not None
            or self.seek is not None
            or self.seek_photo is not None
            or self.redraw
        )


class PlaybackLoop:
    """The player's engine. Commands may come from any thread; step() and run() from one only."""

    def __init__(
        self,
        scene: Scene,
        output: AudioOutput | None,
        deliver: Callable[[Delivery], None],
        notify: Callable[[PlayState], None],
        *,
        clock_factory: ClockFactory = MonotonicClock,
        size: tuple[int, int] = PREVIEW_MAX_SIZE,
    ) -> None:
        self._deliver = deliver
        self._notify_callback = notify
        self._output = output
        self._clock_factory = clock_factory
        # Shared with the command threads (guarded by _cond).
        self._cond = threading.Condition()
        self._requests = _Requests(redraw=True)
        self._want_playing = False
        self._closed = False
        self._idle = False
        self._generation = 0
        self._published = PlayState(False, 0.0, photo_index_at(scene.timeline, 0.0))
        # Render thread only.
        self._scene = scene
        self._size = size
        self._scheduler = FrameScheduler(scene.timeline.fps, scene.timeline.total_frames)
        self._playing = False
        self._position = 0.0
        self._clock: Clock | None = None
        self._output_active = False
        self._redraw = False
        self._index = self._published.photo_index

    # --- Commands (any thread) -------------------------------------------------------------------

    def play(self) -> None:
        with self._cond:
            self._want_playing = True
            self._cond.notify_all()

    def pause(self) -> None:
        with self._cond:
            self._want_playing = False
            self._cond.notify_all()

    def seek(self, t: float) -> None:
        with self._cond:
            self._requests.seek, self._requests.seek_photo = t, None
            self._generation += 1
            self._cond.notify_all()

    def seek_photo(self, index: int) -> None:
        with self._cond:
            self._requests.seek, self._requests.seek_photo = None, index
            self._generation += 1
            self._cond.notify_all()

    def refresh(self) -> None:
        with self._cond:
            self._requests.redraw = True
            self._cond.notify_all()

    def set_scene(self, scene: Scene, at: float | None = None) -> None:
        """A new scene; `at` moves to that instant at the same time (one frame drawn, not two)."""
        with self._cond:
            self._requests.scene, self._requests.scene_at = scene, at
            if at is not None:
                self._requests.seek = self._requests.seek_photo = None
            self._generation += 1
            self._cond.notify_all()

    def set_size(self, width: int, height: int) -> None:
        with self._cond:
            self._requests.size = (max(1, width), max(1, height))
            self._generation += 1
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def generation(self) -> int:
        """Increases with every seek, new scene or size: frames of older generations are stale."""
        return self._generation

    @property
    def playing(self) -> bool:
        """The state asked for (it takes effect on the render thread a moment later)."""
        return self._want_playing

    @property
    def state(self) -> PlayState:
        """The last state published by the render thread (t of the last frame drawn)."""
        with self._cond:
            return self._published

    def wait_idle(self, timeout_s: float) -> bool:
        """Waits until the loop is paused with nothing left to do (tests and closing)."""
        with self._cond:
            return self._cond.wait_for(
                lambda: self._closed or (self._idle and not self._pending()), timeout_s
            )

    # --- Render thread ---------------------------------------------------------------------------

    def run(self) -> None:
        """Runs until close(); stops the sound on the way out."""
        try:
            while self.step():
                pass
        finally:
            self._stop_output()

    def step(self, wait: Waiter | None = None) -> bool:
        """One iteration: apply the requests, then draw a frame or wait. False once closed."""
        with self._cond:
            if self._closed:
                return False
            requests, self._requests = self._requests, _Requests()
            want_playing = self._want_playing
            self._idle = False
        waiter = self._wait if wait is None else wait
        self._apply(requests, want_playing)
        if self._playing:
            self._play_step(waiter)
        elif self._redraw:
            self._redraw = False
            self._draw(self._paused_frame_time(), None)
        else:
            waiter(None)
        return True

    def _pending(self) -> bool:
        return bool(self._requests) or self._want_playing != self._playing

    def _wait(self, timeout_s: float | None) -> None:
        with self._cond:
            if self._closed or self._pending():
                return
            if timeout_s is None:
                self._idle = True
                self._cond.notify_all()
            self._cond.wait(timeout_s)

    def _apply(self, requests: _Requests, want_playing: bool) -> None:
        changed = False
        restart = False
        if requests.scene is not None:
            if self._playing:
                self._position = self._clock_position()
            restart = requests.scene.audio is not self._scene.audio
            self._scene = requests.scene
            timeline = requests.scene.timeline
            self._scheduler = FrameScheduler(timeline.fps, timeline.total_frames, self._scheduler.cost_s)
            self._position = self._clamp(self._position)
            self._redraw = changed = True
        if requests.size is not None:
            self._size = requests.size
            self._scheduler.reset()
            self._redraw = True
        target = requests.seek if requests.scene_at is None else requests.scene_at
        if requests.seek_photo is not None:
            target = photo_start(self._scene.timeline, requests.seek_photo)
        if target is not None:
            self._position = self._clamp(target)
            self._scheduler.reset()
            self._redraw = changed = restart = True
        if requests.redraw:
            self._redraw = True

        if want_playing and not self._playing:
            self._start_playing()
            changed = True
        elif not want_playing and self._playing:
            if target is None and requests.scene is None:
                self._position = self._clock_position()
            self._stop_output()
            self._playing = False
            self._redraw = changed = True
        elif self._playing and restart:
            if target is None:
                self._position = self._clock_position()
            self._stop_output()
            self._start_clock()
            self._scheduler.reset()
        if changed:
            self._publish(self._position)

    def _start_playing(self) -> None:
        timeline = self._scene.timeline
        if timeline.total_frames <= 0:
            with self._cond:
                self._want_playing = False
            return
        if time_to_frame(self._position, timeline.fps) >= timeline.total_frames - 1:
            self._position = 0.0  # at the end: play again from the start
        self._start_clock()
        self._playing = True
        self._scheduler.reset()

    def _play_step(self, wait: Waiter) -> None:
        clock = self._clock
        assert clock is not None
        timeline = self._scene.timeline
        now = clock.now()
        if time_to_frame(now, timeline.fps) >= timeline.total_frames:
            self._finish(clock)
            return
        frame = self._scheduler.next_frame(now)
        if frame is None:
            wait(min(MAX_WAIT_S, max(_MIN_WAIT_S, self._scheduler.wait_s(now))))
            return
        t = frame_to_time(frame, timeline.fps)
        before = clock.now()
        rendered = self._render(t)
        ready = clock.now()
        self._scheduler.drawn(frame, ready - before)
        if rendered is None:
            return
        if ready < t - _EARLY_TOLERANCE_S:
            wait(t - ready)  # ready too soon: it would be ahead of the sound
        self._send(rendered, t, clock)

    def _finish(self, clock: Clock) -> None:
        """The end of the show: last frame, sound off, paused at the end."""
        timeline = self._scene.timeline
        last = timeline.total_frames - 1
        if self._scheduler.last_frame != last:
            self._draw(frame_to_time(last, timeline.fps), clock)
        self._stop_output()
        self._playing = False
        self._position = timeline.total_duration_s
        with self._cond:
            self._want_playing = False
        self._publish(self._position)

    def _draw(self, t: float, clock: Clock | None) -> None:
        rendered = self._render(t)
        if rendered is not None:
            self._send(rendered, t, clock)

    def _render(self, t: float) -> tuple[RGBImage, int] | None:
        """The frame at t and the generation it belongs to (None if it could not be drawn)."""
        with self._cond:
            generation = self._generation
        try:
            return self._scene.frames.frame_at(t, *self._size), generation
        except Exception:  # the preview must never stop for one bad frame
            _log.exception("no s'ha pogut dibuixar la imatge de %.3f s", t)
            return None

    def _send(self, rendered: tuple[RGBImage, int], t: float, clock: Clock | None) -> None:
        image, generation = rendered
        self._deliver(Delivery(image, t, generation, None if clock is None else clock.now()))
        index = photo_index_at(self._scene.timeline, t)
        with self._cond:
            self._published = PlayState(self._playing, t, index)
        if index != self._index:
            self._publish(t)

    def _publish(self, t: float) -> None:
        state = PlayState(self._playing, t, photo_index_at(self._scene.timeline, t))
        self._index = state.photo_index
        with self._cond:
            self._published = state
        self._notify_callback(state)

    # --- Clock and sound -------------------------------------------------------------------------

    def _start_clock(self) -> None:
        audio = self._scene.audio
        if audio is not None and self._output is not None:
            try:
                self._clock = self._output.start(audio, self._position)
                self._output_active = True
                return
            except Exception:
                _log.warning("No s'ha pogut obrir la sortida de so: rellotge intern", exc_info=True)
        self._clock = self._clock_factory(self._position)

    def _stop_output(self) -> None:
        self._clock = None
        if not self._output_active or self._output is None:
            return
        self._output_active = False
        try:
            self._output.stop()
        except Exception:
            _log.warning("No s'ha pogut aturar la sortida de so", exc_info=True)

    def _clock_position(self) -> float:
        return self._position if self._clock is None else self._clamp(self._clock.now())

    def _clamp(self, t: float) -> float:
        return min(max(0.0, t), self._scene.timeline.total_duration_s)

    def _paused_frame_time(self) -> float:
        """The frame on screen at the paused position (the same instant the export would draw)."""
        timeline = self._scene.timeline
        frame = min(time_to_frame(self._position, timeline.fps), max(0, timeline.total_frames - 1))
        return frame_to_time(frame, timeline.fps)
