"""The user's consent to the YouTube notice (ESPECIFICACIO §1.7 bis, "Avís de conformitat", decision 0012).

Consent lives only in the memory of this process: it is never saved (no QSettings, no file, no
project) and is lost when the program closes. Every public function of this module that can open
a connection takes a ConsentToken and calls `require` before doing anything else.
"""

from __future__ import annotations

import threading

from passimaker.youtube.types import YoutubeConsentError

_KEY = object()
_lock = threading.Lock()
_current: ConsentToken | None = None
_serial = 0


class ConsentToken:
    """Proof that the user accepted the notice. Only `grant()` can create one."""

    __slots__ = ("_serial",)

    def __init__(self, key: object, serial: int) -> None:
        if key is not _KEY:
            raise TypeError("ConsentToken is created only by passimaker.youtube.consent.grant()")
        self._serial = serial

    def __repr__(self) -> str:
        return f"ConsentToken(#{self._serial})"


def grant() -> ConsentToken:
    """Records the consent (the user ticked the box and accepted) and returns its token."""
    global _current, _serial
    with _lock:
        if _current is None:
            _serial += 1
            _current = ConsentToken(_KEY, _serial)
        return _current


def current() -> ConsentToken | None:
    """The token of the consent given in this run of the program, or None."""
    with _lock:
        return _current


def revoke() -> None:
    """Withdraws the consent ("Retira la conformitat"): every token given until now stops working."""
    global _current
    with _lock:
        _current = None


def is_valid(token: object) -> bool:
    with _lock:
        return isinstance(token, ConsentToken) and token is _current


def require(token: object) -> None:
    """Raises YoutubeConsentError unless `token` is the current consent. Call it first, before any work."""
    if not is_valid(token):
        raise YoutubeConsentError("no consent" if token is None else "consent withdrawn or invalid")
