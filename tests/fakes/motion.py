"""Fixed motions. Stand in for B3 until it is integrated (not the specification)."""

from __future__ import annotations

from passimaker.model.types import MotionMode, MotionType, PhotoMotion, ResolvedFit, Window

FIXED_WINDOWS: dict[MotionType, tuple[Window, Window]] = {
    MotionType.NONE: (Window(), Window()),
    MotionType.ZOOM_IN: (Window(0.5, 0.5, 1.0), Window(0.5, 0.45, 1.12)),
    MotionType.ZOOM_OUT: (Window(0.5, 0.45, 1.12), Window(0.5, 0.5, 1.0)),
    MotionType.PAN_LEFT: (Window(0.55, 0.5, 1.15), Window(0.45, 0.5, 1.15)),
    MotionType.PAN_RIGHT: (Window(0.45, 0.5, 1.15), Window(0.55, 0.5, 1.15)),
    MotionType.PAN_UP: (Window(0.5, 0.55, 1.15), Window(0.5, 0.45, 1.15)),
    MotionType.PAN_DOWN: (Window(0.5, 0.45, 1.15), Window(0.5, 0.55, 1.15)),
    MotionType.COMBINED: (Window(0.48, 0.48, 1.08), Window(0.54, 0.52, 1.15)),
}


def fixed_motion(motion_type: MotionType, fit: ResolvedFit = ResolvedFit.FILL) -> PhotoMotion:
    start, end = FIXED_WINDOWS[motion_type]
    return PhotoMotion(MotionMode.AUTO, motion_type, 0, start, end, fit)


def fixed_window_at(motion: PhotoMotion, progress: float) -> Window:
    p = min(1.0, max(0.0, progress))
    s, e = motion.start, motion.end
    return Window(
        s.centre_x + (e.centre_x - s.centre_x) * p,
        s.centre_y + (e.centre_y - s.centre_y) * p,
        s.scale + (e.scale - s.scale) * p,
    )
