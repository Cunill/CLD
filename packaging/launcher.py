"""Entry point of the packaged program (PassiMaker.exe, block B12).

`PassiMaker.exe [projecte.pmk]` opens the window; `PassiMaker.exe --autoprova [opcions]` exports a short
video without it and ends with exit code 0 if everything works (passimaker.cli.main_selftest).
From the source tree: `uv run python packaging/launcher.py --autoprova`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SELF_TEST_OPTION = "--autoprova"


def _ensure_streams() -> None:
    """A windowed PassiMaker.exe has no console: sys.stdout and sys.stderr are None unless the caller
    redirected them. Messages written there are then dropped instead of failing."""
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 (open until the end)
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115


def main() -> int:
    _ensure_streams()
    args = sys.argv[1:]
    if args[:1] == [SELF_TEST_OPTION]:
        from passimaker.cli import main_selftest

        return main_selftest(args[1:])
    from passimaker.ui.app import main as main_window

    return main_window(args)


if __name__ == "__main__":
    sys.exit(main())
