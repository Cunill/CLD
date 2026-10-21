"""The compositor: the frame at any time and any size (docs/CONTRACTES.md §7)."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from passimaker.common import PassiMakerError, RGBImage
from passimaker.images import ImageSource
from passimaker.model.types import FitMode, Photo, PhotoMotion, Project, ResolvedFit
from passimaker.motion import FitDecision, base_window, is_inside, resolve_fit, window_at, window_rect
from passimaker.render.canvas import (
    Canvas,
    as_image,
    build_canvas,
    canvas_scale,
    placeholder_canvas,
    requested_long_side,
)
from passimaker.render.params import CANVAS_CACHE_BYTES, EDGE_TOLERANCE_PX, PREFETCH_AHEAD, SENTINEL_COLOR
from passimaker.thumbs import INTERMEDIATE_SIZE
from passimaker.timeline import Timeline, query

type IntermediateProvider = Callable[[Photo], RGBImage]
"""Optional fast path for small output sizes (thumbs.ThumbnailService.get_intermediate)."""

_log = logging.getLogger(__name__)

_FIT_MODE = {ResolvedFit.FILL: FitMode.FILL, ResolvedFit.BLUR: FitMode.BLUR, ResolvedFit.BLACK: FitMode.BLACK}
_STATIC = PhotoMotion()
"""Centred scale-1 window: the whole canvas (FILL: the largest crop with the video aspect)."""
_WEIGHT_EPSILON = 1 / 4096
"""Layer weights closer than this to 0 or 1 are treated as 0 or 1 (invisible in 8 bits)."""

type _CacheKey = tuple[str, int, int]


@dataclass(frozen=True, slots=True)
class _Plan:
    """What the compositor needs to know about one photo (computed once per project)."""

    photo: Photo
    fit: FitDecision
    motion: PhotoMotion
    slot_index: int

    @property
    def max_scale(self) -> float:
        return max(self.motion.start.scale, self.motion.end.scale)


class Compositor:
    """Renders the frame at any time and any size.

    The same instance is used by preview (reduced size) and export (1080p). Thread-safe for
    concurrent frame_at calls from one render thread plus prefetch threads.

    Each photo is drawn from a canvas prepared once per output size (passimaker.render.canvas)
    and warped with sub-pixel precision; the two photos of a crossfade are mixed with the
    opacities of passimaker.timeline.query, and the black fades scale the result. A photo that
    cannot be decoded is drawn as a plain grey canvas (the export checks files beforehand).
    """

    def __init__(
        self,
        project: Project,
        timeline: Timeline,
        image_source: ImageSource,
        intermediate: IntermediateProvider | None = None,
    ) -> None:
        self._timeline = timeline
        self._format = project.output_format
        self._images = image_source
        self._intermediate = intermediate
        photos = {p.id: p for p in project.photos}
        self._plans: dict[str, _Plan] = {}
        for slot in timeline.slots:
            photo = photos.get(slot.photo_id)
            if photo is not None:
                self._plans[photo.id] = _plan(photo, project, slot.index)
        self._order = tuple(slot.photo_id for slot in timeline.slots)
        self._lock = threading.Lock()
        self._cache: OrderedDict[_CacheKey, Canvas] = OrderedDict()
        self._cache_bytes = 0
        self._building: dict[_CacheKey, threading.Lock] = {}
        self._prefetched: set[tuple[str, int]] = set()
        self._failed: set[str] = set()

    def frame_at(self, t: float, width: int, height: int, *, sentinel: bool = False) -> RGBImage:
        if width <= 0 or height <= 0:
            raise ValueError(f"mida d'imatge no vàlida: {width}x{height}")
        visibles = query(self._timeline, t)
        total = sum(layer.opacity for layer in visibles.layers)
        normaliser = max(1.0, total)
        fade = 1.0 - min(1.0, max(0.0, visibles.black_level))
        drawn: list[tuple[RGBImage, float]] = []
        outside = np.zeros((height, width), dtype=bool) if sentinel else None
        for layer in visibles.layers:
            plan = self._plans.get(layer.photo_id)
            weight = layer.opacity / normaliser * fade
            if plan is None or layer.opacity <= 0.0 or (weight <= _WEIGHT_EPSILON and outside is None):
                continue
            image = self._draw(plan, layer.motion_progress, width, height, outside)
            if weight > _WEIGHT_EPSILON:
                drawn.append((image, weight))
        if visibles.layers:
            self._prefetch_after(visibles.layers[-1].photo_id, width, height)
        frame = _mix(drawn, width, height)
        if outside is not None and outside.any():
            frame[outside] = SENTINEL_COLOR
        return frame

    def invalidate(self, photo_ids: frozenset[str] | None = None) -> None:
        """Drops cached canvases (after a fit/rotation change); None drops everything."""
        with self._lock:
            for key in [k for k in self._cache if photo_ids is None or k[0] in photo_ids]:
                self._cache_bytes -= self._cache.pop(key).nbytes
            if photo_ids is None:
                self._prefetched.clear()
            else:
                self._prefetched = {p for p in self._prefetched if p[0] not in photo_ids}

    # --- One layer ------------------------------------------------------------------------------

    def _draw(
        self, plan: _Plan, progress: float, width: int, height: int, outside: np.ndarray | None
    ) -> RGBImage:
        """The photo's canvas seen through its window at `progress`, warped to width x height."""
        canvas = self._canvas(plan, width, height)
        window = window_at(plan.motion, progress)
        left, top, right, bottom = window_rect(window, plan.fit, self._format)
        step_x, step_y = (right - left) / width, (bottom - top) / height
        # Output pixel centre (x + 0.5) -> canvas position -> image pixel index (centre at i + 0.5).
        matrix = np.array(
            [
                [step_x * canvas.scale_x, 0.0, (left + 0.5 * step_x) * canvas.scale_x - 0.5],
                [0.0, step_y * canvas.scale_y, (top + 0.5 * step_y) * canvas.scale_y - 0.5],
            ],
            dtype=np.float64,
        )
        image = as_image(
            cv2.warpAffine(
                canvas.image,
                matrix,
                (width, height),
                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_REPLICATE,
            )
        )
        _clear_outside(image, outside, plan.fit, (left, top), (step_x, step_y))
        return image

    # --- Canvases -------------------------------------------------------------------------------

    def _canvas(self, plan: _Plan, width: int, height: int) -> Canvas:
        key = (plan.photo.id, width, height)
        with self._lock:
            cached = self._cached(key)
            if cached is not None:
                return cached
            building = self._building.setdefault(key, threading.Lock())
        with building:  # one thread builds it; the others wait and then find it in the cache
            with self._lock:
                cached = self._cached(key)
                if cached is not None:
                    return cached
            canvas = self._build(plan, width, height)
            with self._lock:
                self._store(key, canvas)
                self._building.pop(key, None)
        return canvas

    def _cached(self, key: _CacheKey) -> Canvas | None:
        canvas = self._cache.get(key)
        if canvas is not None:
            self._cache.move_to_end(key)
        return canvas

    def _store(self, key: _CacheKey, canvas: Canvas) -> None:
        if key in self._cache:
            return
        self._cache[key] = canvas
        self._cache_bytes += canvas.nbytes
        while self._cache_bytes > CANVAS_CACHE_BYTES and len(self._cache) > 1:
            _, dropped = self._cache.popitem(last=False)
            self._cache_bytes -= dropped.nbytes

    def _build(self, plan: _Plan, width: int, height: int) -> Canvas:
        photo = plan.photo
        # Canvas pixels are source-photo pixels for every fit (passimaker.motion.FitDecision).
        scale = canvas_scale(plan.fit, self._format, plan.max_scale, width, height)
        long_side = requested_long_side(photo.width, photo.height, scale)
        try:
            image = self._fetch(photo, long_side)
        except (PassiMakerError, OSError) as error:
            with self._lock:
                first_failure = photo.id not in self._failed
                self._failed.add(photo.id)
            if first_failure:
                _log.warning("No es pot dibuixar la foto %s: %s", photo.path, error)
            return placeholder_canvas(plan.fit)
        return build_canvas(image, plan.fit, photo.width, photo.height, scale)

    def _fetch(self, photo: Photo, long_side: int) -> RGBImage:
        if self._intermediate is not None and long_side <= INTERMEDIATE_SIZE:
            try:
                image = self._intermediate(photo)
            except (PassiMakerError, OSError):
                image = None
            if image is not None and max(image.shape[:2]) >= min(long_side, max(photo.width, photo.height)):
                return image
        return self._images.get_image(photo, long_side)

    def _prefetch_after(self, photo_id: str, width: int, height: int) -> None:
        """Asks the image source for the next photos, once per photo and size."""
        plan = self._plans.get(photo_id)
        if plan is None:
            return
        upcoming: list[tuple[Photo, int]] = []
        for next_id in self._order[plan.slot_index + 1 : plan.slot_index + 1 + PREFETCH_AHEAD]:
            next_plan = self._plans.get(next_id)
            if next_plan is None:
                continue
            scale = canvas_scale(next_plan.fit, self._format, next_plan.max_scale, width, height)
            long_side = requested_long_side(next_plan.photo.width, next_plan.photo.height, scale)
            upcoming.append((next_plan.photo, long_side))
        with self._lock:
            fresh = [(p, s) for p, s in upcoming if (p.id, s) not in self._prefetched]
            self._prefetched.update((p.id, s) for p, s in fresh)
        for photo, long_side in fresh:
            self._images.prefetch([photo], long_side)


def _plan(photo: Photo, project: Project, slot_index: int) -> _Plan:
    """Fit and motion of a photo; static when motion is off or the stored motion does not fit.

    The stored motion was drawn for the fit the controller resolved; if it no longer matches the
    photo (e.g. a project edited by hand) the whole canvas is shown instead of risking borders.
    """
    fit = resolve_fit(photo.width, photo.height, project.output_format, photo.fit)
    motion = photo.motion
    if not project.motion_enabled:
        return _Plan(photo, fit, _STATIC, slot_index)
    base = base_window(fit.canvas_width, fit.canvas_height, project.output_format)
    inside = is_inside(motion.start, base) and is_inside(motion.end, base)
    if motion.resolved_fit is not fit.fit or not inside:
        _log.warning("Moviment no vàlid per a la foto %s: es mostra sencera", photo.path)
        return _Plan(photo, fit, _STATIC, slot_index)
    return _Plan(photo, fit, motion, slot_index)


def _clear_outside(
    image: RGBImage,
    outside: np.ndarray | None,
    fit: FitDecision,
    origin: tuple[float, float],
    step: tuple[float, float],
) -> None:
    """Output pixels whose centre falls outside the canvas: black, and marked in sentinel mode.

    By construction (passimaker.motion) windows stay inside the canvas, so this is normally empty.
    """
    height, width = image.shape[:2]
    first_x, last_x = _inside_range(origin[0], step[0], fit.canvas_width, width)
    first_y, last_y = _inside_range(origin[1], step[1], fit.canvas_height, height)
    if first_x == 0 and first_y == 0 and last_x == width - 1 and last_y == height - 1:
        return
    targets: list[np.ndarray] = [image] if outside is None else [image, outside]
    for target in targets:
        value = 0 if target is image else True
        if first_x > last_x or first_y > last_y:
            target[:] = value
            continue
        target[:first_y] = value
        target[last_y + 1 :] = value
        target[:, :first_x] = value
        target[:, last_x + 1 :] = value


def _inside_range(origin: float, step: float, size: int, count: int) -> tuple[int, int]:
    """First and last output pixel whose centre maps inside [0, size] along one axis."""
    # Canvas position of pixel i: origin + (i + 0.5) * step, which must lie in [0, size].
    low = (0.0 - origin) / step - 0.5 - EDGE_TOLERANCE_PX
    high = (size - origin) / step - 0.5 + EDGE_TOLERANCE_PX
    return max(0, int(np.ceil(low))), min(count - 1, int(np.floor(high)))


def _mix(drawn: list[tuple[RGBImage, float]], width: int, height: int) -> RGBImage:
    """Weighted sum of the layers (weights already include the black fade); black elsewhere."""
    if not drawn:
        return np.zeros((height, width, 3), dtype=np.uint8)
    if len(drawn) == 1:
        image, weight = drawn[0]
        if weight >= 1.0 - _WEIGHT_EPSILON:
            return image
        return as_image(cv2.convertScaleAbs(image, alpha=weight))
    (below, w_below), (above, w_above) = drawn[0], drawn[1]
    return as_image(cv2.addWeighted(below, w_below, above, w_above, 0.0))
