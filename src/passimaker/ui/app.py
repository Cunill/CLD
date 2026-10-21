"""Application entry point (`passimaker`). Implemented in block B10."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Starts the GUI. Optional argument: a .pmk file to open."""
    args = sys.argv[1:] if argv is None else argv
    raise NotImplementedError(f"B10 (args: {args})")
