"""Motion drawing: choice of motion per photo (balance rules) and construction of its windows.

Every photo gets an *option*: a motion type plus, for combined motions, the zoom direction and
the diagonal. The automatic draw chooses options with weighted random choice under the
balance rules of §1.5; the windows are then built so that both ends are inside the canvas
(which guarantees every intermediate window is inside, see geometry.py).

Randomness comes only from the project seed, the photo id and its draw count.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from passi.model.types import (
    Intensity,
    MotionMode,
    MotionType,
    OutputFormat,
    PhotoMotion,
    ResolvedFit,
    Window,
)
from passi.motion.geometry import FitDecision, base_window, centre_range, is_inside
from passi.motion.params import (
    BALANCE_WINDOW,
    BASE_PROBABILITIES,
    BLUR_INTENSITY_FACTOR,
    COMBINED_PAN_FACTOR,
    COMBINED_ZOOM_FACTOR,
    FOCAL_JITTER,
    FOCAL_POINT,
    INTENSITY_PARAMS,
    MAX_FAMILY_RUN,
    MAX_UPSCALE,
    MAX_ZOOM_IMBALANCE,
    MIN_PAN,
    MIN_ZOOM,
    NO_MOTION_BELOW,
    PREFERRED_PAN_AXIS_SHARE,
    RULE_COMPENSATION,
    IntensityParams,
)

MIN_VISIBLE_DURATION_S = 0.5


@dataclass(frozen=True, slots=True)
class MotionRequest:
    photo_id: str
    width: int
    """Photo size after EXIF orientation and manual rotation."""
    height: int
    visible_duration_s: float
    """Time the photo is on screen (its slot widened by half of each crossfade)."""
    fit: FitDecision
    output_format: OutputFormat
    mode: MotionMode
    manual_type: MotionType | None
    """Fixed type for MANUAL mode."""
    draw_count: int
    current: PhotoMotion | None = None
    """The photo's current motion (None if it has never been drawn)."""


class Family(Enum):
    ZOOM = "zoom"
    PAN = "pan"
    COMBINED = "combined"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Option:
    type: MotionType
    zoom: int = 0
    """+1 zoom in, -1 zoom out, 0 no zoom."""
    dx: int = 0
    """Direction of the window movement: +1 right/down, -1 left/up, 0 none."""
    dy: int = 0

    @property
    def family(self) -> Family:
        if self.type in (MotionType.ZOOM_IN, MotionType.ZOOM_OUT):
            return Family.ZOOM
        if self.type is MotionType.COMBINED:
            return Family.COMBINED
        if self.type is MotionType.NONE:
            return Family.NONE
        return Family.PAN


ZOOM_IN = Option(MotionType.ZOOM_IN, zoom=1)
ZOOM_OUT = Option(MotionType.ZOOM_OUT, zoom=-1)
PAN_LEFT = Option(MotionType.PAN_LEFT, dx=-1)
PAN_RIGHT = Option(MotionType.PAN_RIGHT, dx=1)
PAN_UP = Option(MotionType.PAN_UP, dy=-1)
PAN_DOWN = Option(MotionType.PAN_DOWN, dy=1)
STILL = Option(MotionType.NONE)
COMBINED_OPTIONS = tuple(
    Option(MotionType.COMBINED, zoom=z, dx=dx, dy=dy) for z in (1, -1) for dx in (-1, 1) for dy in (-1, 1)
)
PAN_OPTIONS = (PAN_LEFT, PAN_RIGHT, PAN_UP, PAN_DOWN)
ALL_OPTIONS = (ZOOM_IN, ZOOM_OUT, *PAN_OPTIONS, *COMBINED_OPTIONS, STILL)
_BY_TYPE = {o.type: o for o in (ZOOM_IN, ZOOM_OUT, *PAN_OPTIONS, STILL)}


def option_of(motion: PhotoMotion) -> Option:
    """Recovers the option of an existing motion (for neighbours and rebuilds)."""
    if motion.type is not MotionType.COMBINED:
        return _BY_TYPE[motion.type]
    zoom = 1 if motion.end.scale >= motion.start.scale else -1
    dx = -1 if motion.end.centre_x < motion.start.centre_x else 1
    dy = -1 if motion.end.centre_y < motion.start.centre_y else 1
    return Option(MotionType.COMBINED, zoom=zoom, dx=dx, dy=dy)


def _rng(seed: int, photo_id: str, draw_count: int, salt: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}|{photo_id}|{draw_count}|{salt}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# --- Window construction -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Context:
    base_x: float
    base_y: float
    duration: float
    scale_cap: float
    """Maximum scale allowed by MAX_UPSCALE (at least 1)."""
    still_only: bool
    fill: bool
    focal_x: float
    focal_y: float


def _context(request: MotionRequest, focal: tuple[float, float]) -> _Context:
    fit = request.fit
    base_x, base_y = base_window(fit.canvas_width, fit.canvas_height, request.output_format)
    out_width = request.output_format.size[0]
    # Source pixels covered by the scale-1 window (canvas pixels are photo pixels, also for
    # composed canvases).
    window_px = fit.canvas_width * base_x
    return _Context(
        base_x=base_x,
        base_y=base_y,
        duration=max(request.visible_duration_s, MIN_VISIBLE_DURATION_S),
        scale_cap=max(1.0, MAX_UPSCALE * window_px / out_width),
        still_only=window_px < NO_MOTION_BELOW * out_width,
        fill=fit.fit is ResolvedFit.FILL,
        focal_x=focal[0],
        focal_y=focal[1],
    )


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _fit_pair(c0: float, c1: float, size0: float, size1: float) -> tuple[float, float]:
    """Shifts both centres together so both windows are inside, keeping their distance."""
    low0, high0 = centre_range(size0)
    low1, high1 = centre_range(size1)
    shift_min = max(low0 - c0, low1 - c1)
    shift_max = min(high0 - c0, high1 - c1)
    if shift_min <= shift_max:
        shift = _clamp(0.0, shift_min, shift_max)
        return c0 + shift, c1 + shift
    return _clamp(c0, low0, high0), _clamp(c1, low1, high1)


def _windows(ctx: _Context, s0: float, s1: float, move_x: float, move_y: float) -> tuple[Window, Window]:
    """End windows with scales s0 -> s1, centred on the focal point and moving by (move_x, move_y)."""
    w0x, w1x = ctx.base_x / s0, ctx.base_x / s1
    w0y, w1y = ctx.base_y / s0, ctx.base_y / s1
    x0, x1 = _fit_pair(ctx.focal_x - move_x / 2, ctx.focal_x + move_x / 2, w0x, w1x)
    y0, y1 = _fit_pair(ctx.focal_y - move_y / 2, ctx.focal_y + move_y / 2, w0y, w1y)
    return Window(x0, y0, s0), Window(x1, y1, s1)


def _zoom_amount(ctx: _Context, params: IntensityParams, factor: float = 1.0) -> float:
    amount = params.zoom_amount * factor * (1.0 if ctx.fill else BLUR_INTENSITY_FACTOR)
    return min(amount, params.max_zoom_speed * ctx.duration)


def _pan_amount(ctx: _Context, params: IntensityParams, factor: float = 1.0) -> float:
    return min(params.pan_amount * factor, params.max_pan_speed * ctx.duration)


def _build_zoom(ctx: _Context, params: IntensityParams, zoom: int) -> tuple[Window, Window] | None:
    amount = min(_zoom_amount(ctx, params), ctx.scale_cap - 1.0)
    if amount < MIN_ZOOM:
        return None
    start, end = _windows(ctx, 1.0, 1.0 + amount, 0.0, 0.0)
    return (start, end) if zoom > 0 else (end, start)


def _pan_scale(base: float, amount: float, cap: float) -> tuple[float, float] | None:
    """Scale needed to move by `amount` window sides along an axis of size `base`, and the
    amount actually possible under the upscale cap."""
    needed = base * (1.0 + amount)
    if needed <= 1.0:
        return 1.0, amount
    if needed <= cap:
        return needed, amount
    reduced = cap / base - 1.0
    return (cap, reduced) if reduced >= MIN_PAN else None


def _build_pan(ctx: _Context, params: IntensityParams, option: Option) -> tuple[Window, Window] | None:
    if not ctx.fill:
        return None
    base = ctx.base_x if option.dx else ctx.base_y
    planned = _pan_amount(ctx, params)
    if planned < MIN_PAN:
        return None
    result = _pan_scale(base, planned, ctx.scale_cap)
    if result is None:
        return None
    scale, amount = result
    window = base / scale
    distance = min(amount * window, 1.0 - window) * (1.0 - 1e-9)
    return _windows(ctx, scale, scale, option.dx * distance, option.dy * distance)


def _build_combined(ctx: _Context, params: IntensityParams, option: Option) -> tuple[Window, Window] | None:
    if not ctx.fill:
        return None
    zoom = _zoom_amount(ctx, params, COMBINED_ZOOM_FACTOR)
    # The diagonal displacement is COMBINED_PAN_FACTOR of a pure pan; each axis gets 1/sqrt(2).
    pan = _pan_amount(ctx, params, COMBINED_PAN_FACTOR) / math.sqrt(2.0)
    biggest_base = max(ctx.base_x, ctx.base_y)
    result = _pan_scale(biggest_base, pan, ctx.scale_cap)
    if result is None:
        return None
    large_window_scale, pan = result
    zoom = min(zoom, ctx.scale_cap / large_window_scale - 1.0)
    if zoom < MIN_ZOOM or pan * math.sqrt(2.0) < MIN_PAN:
        return None
    small_window_scale = large_window_scale * (1.0 + zoom)
    # Displacement measured against the smallest window, so the perceived speed never exceeds the cap.
    move_x = pan * ctx.base_x / small_window_scale
    move_y = pan * ctx.base_y / small_window_scale
    move_x = min(move_x, 1.0 - ctx.base_x / large_window_scale) * (1.0 - 1e-9)
    move_y = min(move_y, 1.0 - ctx.base_y / large_window_scale) * (1.0 - 1e-9)
    s0, s1 = (
        (large_window_scale, small_window_scale)
        if option.zoom > 0
        else (small_window_scale, large_window_scale)
    )
    return _windows(ctx, s0, s1, option.dx * move_x, option.dy * move_y)


def _build(ctx: _Context, params: IntensityParams, option: Option) -> tuple[Window, Window] | None:
    """End windows for an option, or None if the option is not feasible for this photo."""
    if option is STILL or option.type is MotionType.NONE:
        still = _windows(ctx, 1.0, 1.0, 0.0, 0.0)[0]
        return still, still
    if ctx.still_only:
        return None
    if option.family is Family.ZOOM:
        windows = _build_zoom(ctx, params, option.zoom)
    elif option.family is Family.PAN:
        windows = _build_pan(ctx, params, option)
    else:
        windows = _build_combined(ctx, params, option)
    if windows is None:
        return None
    base = (ctx.base_x, ctx.base_y)
    if not (is_inside(windows[0], base) and is_inside(windows[1], base)):
        return None
    return windows


# --- Choice under the balance rules --------------------------------------------------------


def _weights(ctx: _Context, options: Sequence[Option]) -> list[float]:
    slack_x, slack_y = 1.0 - ctx.base_x, 1.0 - ctx.base_y
    pan_total = sum(BASE_PROBABILITIES[o.type] for o in PAN_OPTIONS)
    preferred: str | None = None
    if abs(slack_x - slack_y) > 0.02:
        preferred = "x" if slack_x > slack_y else "y"
    weights: list[float] = []
    for option in options:
        if option.family is Family.PAN:
            if preferred is None:
                weights.append(pan_total / 4)
            else:
                on_axis = (option.dx != 0) == (preferred == "x")
                share = PREFERRED_PAN_AXIS_SHARE if on_axis else 1.0 - PREFERRED_PAN_AXIS_SHARE
                weights.append(pan_total * share / 2)
        elif option.family is Family.COMBINED:
            weights.append(BASE_PROBABILITIES[MotionType.COMBINED] / len(COMBINED_OPTIONS))
        elif option.family is Family.ZOOM:
            weights.append(BASE_PROBABILITIES[option.type])
        else:
            weights.append(0.0)
    return [w * RULE_COMPENSATION.get(o.type, 1.0) for w, o in zip(weights, options, strict=True)]


def _choose(rng: random.Random, options: Sequence[Option], weights: Sequence[float]) -> Option:
    total = sum(weights)
    if total <= 0:
        return options[0]
    target = rng.random() * total
    for option, weight in zip(options, weights, strict=True):
        target -= weight
        if target < 0:
            return option
    return options[-1]


def _zoom_sign(option: Option | None) -> int:
    return 0 if option is None else option.zoom


class _Rules:
    """Balance rules evaluated against the options already known in the sequence."""

    def __init__(self, options: list[Option | None]) -> None:
        self.options = options

    def differs_from_neighbours(self, index: int, candidate: Option) -> bool:
        """Rule 1: never the same type and direction twice in a row."""
        neighbours = [self._at(index - 1), self._at(index + 1)]
        return all(n != candidate for n in neighbours)

    def family_run_ok(self, index: int, candidate: Option) -> bool:
        """Rule 2: at most MAX_FAMILY_RUN consecutive photos of the same family."""
        family = candidate.family
        if family is Family.NONE:
            return True
        run = 1
        i = index - 1
        while (o := self._at(i)) is not None and o.family is family:
            run += 1
            i -= 1
        i = index + 1
        while (o := self._at(i)) is not None and o.family is family:
            run += 1
            i += 1
        return run <= MAX_FAMILY_RUN

    def zoom_balance_ok(self, index: int, candidate: Option) -> bool:
        """Rule 3: in any BALANCE_WINDOW consecutive photos, |zoom in - zoom out| <= MAX_ZOOM_IMBALANCE."""
        n = len(self.options)
        size = min(BALANCE_WINDOW, n)
        for start in range(max(0, index - size + 1), min(index, n - size) + 1):
            total = 0
            for i in range(start, start + size):
                total += candidate.zoom if i == index else _zoom_sign(self._at(i))
            if abs(total) > MAX_ZOOM_IMBALANCE:
                return False
        return True

    def _at(self, index: int) -> Option | None:
        if 0 <= index < len(self.options):
            return self.options[index]
        return None


def _manual_option(request: MotionRequest, rng: random.Random) -> list[Option]:
    """Options matching the manual type, in preference order (combined: random diagonal first)."""
    manual = request.manual_type or MotionType.NONE
    if manual is MotionType.COMBINED:
        shuffled = list(COMBINED_OPTIONS)
        rng.shuffle(shuffled)
        return shuffled
    return [_BY_TYPE[manual]]


def _motion(request: MotionRequest, option: Option, windows: tuple[Window, Window]) -> PhotoMotion:
    return PhotoMotion(
        mode=request.mode,
        type=option.type,
        draw_count=request.draw_count,
        start=windows[0],
        end=windows[1],
        resolved_fit=request.fit.fit,
    )


def _focal(request: MotionRequest, seed: int) -> tuple[float, float]:
    rng = _rng(seed, request.photo_id, request.draw_count, "focal")
    return (
        FOCAL_POINT[0] + rng.uniform(-FOCAL_JITTER[0], FOCAL_JITTER[0]),
        FOCAL_POINT[1] + rng.uniform(-FOCAL_JITTER[1], FOCAL_JITTER[1]),
    )


def _feasible(ctx: _Context, params: IntensityParams) -> dict[Option, tuple[Window, Window]]:
    built: dict[Option, tuple[Window, Window]] = {}
    for option in ALL_OPTIONS:
        windows = _build(ctx, params, option)
        if windows is not None:
            built[option] = windows
    return built


def _draw_one(
    index: int,
    request: MotionRequest,
    seed: int,
    params: IntensityParams,
    rules: _Rules,
    total: int,
    reroll: bool,
) -> tuple[Option, PhotoMotion]:
    ctx = _context(request, _focal(request, seed))
    feasible = _feasible(ctx, params)
    rng = _rng(seed, request.photo_id, request.draw_count, "type")

    if request.mode is MotionMode.MANUAL:
        for option in _manual_option(request, rng):
            if option in feasible:
                return option, _motion(request, option, feasible[option])
        return STILL, _motion(request, STILL, feasible[STILL])

    candidates = [o for o in feasible if o is not STILL] or [STILL]
    excluded = option_of(request.current) if (reroll and request.current is not None) else None
    filters: list[Callable[[Option], bool]] = []
    if excluded is not None:
        filters.append(lambda o: o != excluded)
    if index == 0:
        filters.append(lambda o: o == ZOOM_IN)
    elif index == total - 1:
        filters.append(lambda o: o == ZOOM_OUT)
    filters.append(lambda o: rules.differs_from_neighbours(index, o))
    filters.append(lambda o: rules.zoom_balance_ok(index, o))
    filters.append(lambda o: rules.family_run_ok(index, o))
    for keep in filters:
        filtered = [o for o in candidates if keep(o)]
        if filtered:
            candidates = filtered
    option = _choose(rng, candidates, _weights(ctx, candidates))
    return option, _motion(request, option, feasible[option])


def _preset_first_and_last(
    requests: Sequence[MotionRequest],
    known: list[Option | None],
    drawn: list[bool],
    which: frozenset[str] | None,
    seed: int,
    params: IntensityParams,
) -> None:
    """Rule 4 is decided before the rest, so the other photos take it into account."""
    edges = [(0, ZOOM_IN), (len(requests) - 1, ZOOM_OUT)] if requests else []
    for index, option in edges[: 1 if len(requests) == 1 else 2]:
        request = requests[index]
        is_reroll = which is not None and request.photo_id in which and request.current is not None
        if not drawn[index] or request.mode is not MotionMode.AUTO or is_reroll:
            continue
        if _build(_context(request, _focal(request, seed)), params, option) is not None:
            known[index] = option


def draw_motions(
    requests: Sequence[MotionRequest],
    seed: int,
    intensity: Intensity,
    which: frozenset[str] | None = None,
) -> dict[str, PhotoMotion]:
    """Draws motions applying the balance rules of §1.5. Deterministic for a given seed.

    - which=None: first draw of every photo (initial import, "reset all").
    - which=set of ids: those photos are drawn again ("draw again"); if they already had an
      automatic motion, the new one is different. Other photos keep their current motion and
      act as neighbours for the rules. Photos without a current motion are always drawn.
    - MANUAL photos get their fixed type (only the geometry is computed).

    Returns the motion of every request, keyed by photo id.
    """
    params = INTENSITY_PARAMS[intensity]
    known: list[Option | None] = [
        None if (which is None or r.photo_id in which or r.current is None) else option_of(r.current)
        for r in requests
    ]
    drawn = [o is None for o in known]
    _preset_first_and_last(requests, known, drawn, which, seed, params)
    rules = _Rules(known)
    result: dict[str, PhotoMotion] = {}
    for index, request in enumerate(requests):
        if not drawn[index] and request.current is not None:
            result[request.photo_id] = request.current
            continue
        reroll = which is not None and request.photo_id in which
        option, motion = _draw_one(index, request, seed, params, rules, len(requests), reroll)
        known[index] = option
        result[request.photo_id] = motion
    return result


def rebuild_motions(
    requests: Sequence[MotionRequest], seed: int, intensity: Intensity
) -> dict[str, PhotoMotion]:
    """Recomputes the windows keeping each photo's motion type (after a change of output
    format, fit, rotation, duration or intensity). Photos whose type is no longer feasible,
    or that have no motion yet, are drawn with the automatic rules."""
    params = INTENSITY_PARAMS[intensity]
    known: list[Option | None] = [None if r.current is None else option_of(r.current) for r in requests]
    rules = _Rules(known)
    result: dict[str, PhotoMotion] = {}
    for index, request in enumerate(requests):
        ctx = _context(request, _focal(request, seed))
        option = known[index]
        if request.mode is MotionMode.MANUAL or option is None:
            option, motion = _draw_one(index, request, seed, params, rules, len(requests), reroll=False)
        else:
            windows = _build(ctx, params, option)
            if windows is None:
                known[index] = None
                option, motion = _draw_one(index, request, seed, params, rules, len(requests), reroll=False)
            else:
                motion = _motion(request, option, windows)
        known[index] = option
        result[request.photo_id] = motion
    return result


def motion_speeds(motion: PhotoMotion, base: tuple[float, float], duration_s: float) -> tuple[float, float]:
    """(zoom speed, pan speed) of a motion, in the units of IntensityParams, for tests and tools."""
    duration = max(duration_s, MIN_VISIBLE_DURATION_S)
    s0, s1 = motion.start.scale, motion.end.scale
    zoom = (max(s0, s1) / min(s0, s1) - 1.0) / duration
    smallest = max(s0, s1)
    pan_x = abs(motion.end.centre_x - motion.start.centre_x) / (base[0] / smallest)
    pan_y = abs(motion.end.centre_y - motion.start.centre_y) / (base[1] / smallest)
    return zoom, math.hypot(pan_x, pan_y) / duration
