"""M7 · Frame compositor, shared by preview and export (block B6)."""

from __future__ import annotations

from collections.abc import Callable

from passimaker.common import RGBImage
from passimaker.images import ImageSource
from passimaker.model.types import Photo, Project
from passimaker.timeline import Timeline

SENTINEL_COLOR: tuple[int, int, int] = (255, 0, 255)
"""In sentinel mode every pixel outside the photo canvas is painted with this colour."""

type IntermediateProvider = Callable[[Photo], RGBImage]
"""Optional fast path for small output sizes (thumbs.ThumbnailService.get_intermediate)."""


class Compositor:
    """Renders the frame at any time and any size.

    The same instance is used by preview (reduced size) and export (1080p). Thread-safe for
    concurrent frame_at calls from one render thread plus prefetch threads.
    """

    def __init__(
        self,
        project: Project,
        timeline: Timeline,
        image_source: ImageSource,
        intermediate: IntermediateProvider | None = None,
    ) -> None:
        raise NotImplementedError("B6")

    def frame_at(self, t: float, width: int, height: int, *, sentinel: bool = False) -> RGBImage:
        raise NotImplementedError("B6")

    def invalidate(self, photo_ids: frozenset[str] | None = None) -> None:
        """Drops cached canvases (after a fit/rotation change); None drops everything."""
        raise NotImplementedError("B6")
