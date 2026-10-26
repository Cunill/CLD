"""Safe file names for the songs the program writes: YouTube and recordings (contract §15 and §16).

Moved from passimaker.youtube.files in block C09; passimaker.youtube still exports safe_target_path.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

EXTENSION = ".mp3"
FALLBACK_NAME = "Cançó"
"""For a title with nothing usable left (only reserved characters or dots); callers pass their own."""
MAX_NAME_UNITS = 150
"""Longest name without the extension, in UTF-16 code units (what Windows counts; an emoji is 2)."""
MAX_NAME_BYTES = 200
"""And at most this many bytes in UTF-8: Linux and network drives (Samba) allow 255 bytes per name."""
MIN_NAME_UNITS = 20
"""Even in a very deep folder, names keep at least this much (long paths work on recent Windows)."""
WINDOWS_MAX_PATH = 259
"""MAX_PATH (260) minus the final NUL: keeps the whole path usable by every Windows program."""
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in "123456789¹²³"}
_SUFFIX_UNITS = len(" (9999)") + len(EXTENSION)


def safe_target_path(folder: Path, title: str, *, fallback: str = FALLBACK_NAME) -> Path:
    """A free path `<folder>/<title>.mp3`, valid on Windows; `<title> (2).mp3`… if taken.

    Never an existing file. The title loses the characters Windows forbids (< > : " / \\ | ? * and
    control characters), trailing dots and spaces, and is cut to fit; a reserved device name (CON,
    NUL, COM1…, also as "con.txt") gets a "_" in front; with nothing left it is `fallback`.
    """
    room = WINDOWS_MAX_PATH - _units(str(folder)) - 1 - _SUFFIX_UNITS
    budget = max(MIN_NAME_UNITS, min(MAX_NAME_UNITS, room))
    name = safe_name(title, budget, fallback=fallback)
    candidate = folder / f"{name}{EXTENSION}"
    number = 2
    while _taken(candidate):
        candidate = folder / f"{name} ({number}){EXTENSION}"
        number += 1
    return candidate


def safe_name(title: str, max_units: int = MAX_NAME_UNITS, *, fallback: str = FALLBACK_NAME) -> str:
    """`title` as a file name valid on Windows, without extension, at most `max_units` UTF-16 units."""
    text = unicodedata.normalize("NFC", title)
    text = _INVALID.sub(" ", text)
    text = " ".join(text.split())
    text = _cut(text, max_units).strip(" .")
    if not text:
        return fallback
    if text.split(".")[0].rstrip(" ").upper() in _RESERVED:
        text = "_" + _cut(text, max_units - 1)
    return text


def _cut(text: str, max_units: int) -> str:
    """The longest start of `text` within `max_units` UTF-16 units and MAX_NAME_BYTES UTF-8 bytes,
    never splitting a character."""
    units = size = 0
    for index, char in enumerate(text):
        units += _units(char)
        size += len(char.encode("utf-8", "surrogatepass"))
        if units > max_units or size > MAX_NAME_BYTES:
            return text[:index].rstrip(" .")
    return text


def _units(text: str) -> int:
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _taken(path: Path) -> bool:
    # exists() follows links: a broken link also takes the name. On Windows the check ignores case.
    return path.exists() or path.is_symlink()
