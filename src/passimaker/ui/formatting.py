"""Number and time formatting shared by the storyboard, the panels and the status bar.

These helpers build text out of numbers only; every word around them comes from ``tr()``.
"""

from __future__ import annotations


def clock(seconds: float) -> str:
    """``4:30`` (minutes:seconds), as in the status bar of §1.0."""
    total = max(0, round(seconds))
    return f"{total // 60}:{total % 60:02d}"


SECONDS_SYMBOL = " s"
"""Unit symbol, not prose: the same in Catalan and in every language the program may get."""


def duration(seconds: float) -> str:
    """``2,0 s`` with a comma, the decimal separator in Catalan (§1.2)."""
    return f"{seconds:.1f}".replace(".", ",") + SECONDS_SYMBOL


MEGABYTE = 1_000_000
MEGABYTE_SYMBOL = " MB"


def megabytes(size_bytes: int) -> str:
    """``245 MB``, or ``8,4 MB`` under ten, as in "Vídeo desat (4:30, 245 MB)" (§1.9)."""
    value = size_bytes / MEGABYTE
    text = f"{value:.0f}" if value >= 10 else f"{value:.1f}".replace(".", ",")
    return text + MEGABYTE_SYMBOL
