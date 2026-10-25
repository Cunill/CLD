"""The temporary WAV, written while recording and deleted on any interruption (block C09)."""

from __future__ import annotations

from pathlib import Path

TEMP_PREFIX = "passimaker_gravacio_"
"""Temporary WAVs are `<temp_dir>/passimaker_gravacio_*.wav` (32-bit float)."""


def remove_leftovers(temp_dir: Path) -> int:
    """Delete the temporary WAVs left by an unexpected close; the number deleted.

    Called when the program opens (G1: an interrupted recording is never recovered).
    """
    raise NotImplementedError("passimaker.recorder: implemented in block C09")
