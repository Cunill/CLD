"""Where the export keeps its caches (until B12 gathers every program location in one place)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

CACHE_ENV_VAR = "PASSIMAKER_CACHE"
"""Folder for the caches; takes precedence over the default (tests point it to a temporary folder)."""

AUDIO_CACHE_SUBDIR = "audio"
"""Each cache has its own subfolder: the thumbnail cache (B5) cleans only its own."""


def cache_root() -> Path:
    """%LOCALAPPDATA%\\PassiMaker\\cache on Windows (PLA, B12); ~/.cache/passimaker elsewhere."""
    override = os.environ.get(CACHE_ENV_VAR)
    if override:
        return Path(override)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "PassiMaker" / "cache"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "passimaker"


def audio_cache_dir() -> Path:
    return cache_root() / AUDIO_CACHE_SUBDIR
