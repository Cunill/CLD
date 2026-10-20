"""Translations. UI text uses Qt's tr(); the Catalan catalogue (ca.ts / ca.qm) arrives in B10.

Non-Qt modules raise errors with a `message_key`; MESSAGES maps keys to Catalan text.
"""

from __future__ import annotations

from collections.abc import Mapping

MESSAGES: Mapping[str, str] = {}


def message(key: str) -> str:
    """Catalan text for a message key (falls back to the key itself)."""
    return MESSAGES.get(key, key)
