"""Keeping the computer awake while exporting (ESPECIFICACIO §1.9)."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Generator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def set_execution_state(flags: int) -> bool:
    """Windows SetThreadExecutionState for the calling thread; does nothing elsewhere (returns False)."""
    if sys.platform == "win32":
        return ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags)) != 0
    return False


@contextmanager
def keep_awake() -> Generator[None]:
    """The system does not go to sleep inside the block (the screen may still turn off).

    The state belongs to the thread, so enter and leave on the same thread.
    """
    set_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        set_execution_state(ES_CONTINUOUS)
