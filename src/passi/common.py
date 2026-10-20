"""Shared infrastructure types used by every module (no Qt, no business logic)."""

from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

type RGBImage = NDArray[np.uint8]
"""An image as a NumPy array of shape (height, width, 3), dtype uint8, sRGB."""

type AudioBlock = NDArray[np.float32]
"""A block of audio samples of shape (frames, 2), float32 in [-1, 1], 48 kHz stereo."""

type ProgressCallback = Callable[[int, int], None]
"""Called as progress(done, total). Must be cheap; may be called from worker threads."""


class CancelToken:
    """Thread-safe cancellation flag shared between a caller and a long-running task."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class PassiError(Exception):
    """Base error. `message_key` identifies a translatable user-facing message (see i18n)."""

    def __init__(self, message_key: str, detail: str = "") -> None:
        super().__init__(f"{message_key}: {detail}" if detail else message_key)
        self.message_key = message_key
        self.detail = detail
