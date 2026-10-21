"""M7 · Frame compositor, shared by preview and export (block B6).

Public API (docs/CONTRACTES.md §7): Compositor, SENTINEL_COLOR and IntermediateProvider.
"""

from __future__ import annotations

from passimaker.render.compositor import Compositor, IntermediateProvider
from passimaker.render.params import SENTINEL_COLOR

__all__ = ["SENTINEL_COLOR", "Compositor", "IntermediateProvider"]
