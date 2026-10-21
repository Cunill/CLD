"""Finding ffmpeg and ffprobe."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from passimaker.ffmpeg._process import os_path
from passimaker.ffmpeg.types import ENV_VAR, ERROR_NOT_FOUND, FfmpegError, FfmpegPaths

REPO_ROOT = Path(__file__).resolve().parents[3]
VENDOR_DIR = REPO_ROOT / "vendor" / "ffmpeg" / "bin"
"""Copy fixed by tools/obtenir_ffmpeg.ps1 when running from the source tree."""


def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _in_dir(directory: Path) -> FfmpegPaths | None:
    ffmpeg = directory / _exe("ffmpeg")
    ffprobe = directory / _exe("ffprobe")
    if Path(os_path(ffmpeg)).is_file() and Path(os_path(ffprobe)).is_file():
        return FfmpegPaths(ffmpeg, ffprobe)
    return None


def program_dirs() -> list[Path]:
    """Folders of the packaged program (PyInstaller): next to PassiMaker.exe and its data folder."""
    if not getattr(sys, "frozen", False):
        return []
    dirs = [Path(sys.executable).resolve().parent]
    bundle = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle, str) and Path(bundle) not in dirs:
        dirs.append(Path(bundle))
    return dirs


def locate() -> FfmpegPaths:
    """Search order: PASSIMAKER_FFMPEG, the program folder, vendor/ffmpeg/bin, PATH.

    If PASSIMAKER_FFMPEG is set it must be right: a wrong value is an error, not a silent fallback.
    """
    env = os.environ.get(ENV_VAR)
    if env:
        found = _in_dir(Path(env))
        if found is None:
            raise FfmpegError(ERROR_NOT_FOUND, f"{ENV_VAR}={env}: no hi ha ffmpeg i ffprobe")
        return found
    searched = [*program_dirs(), VENDOR_DIR]
    for directory in searched:
        found = _in_dir(directory)
        if found is not None:
            return found
    ffmpeg = shutil.which(_exe("ffmpeg"))
    ffprobe = shutil.which(_exe("ffprobe"))
    if ffmpeg is not None and ffprobe is not None:
        return FfmpegPaths(Path(ffmpeg), Path(ffprobe))
    places = ", ".join([*(str(d) for d in searched), "PATH"])
    raise FfmpegError(ERROR_NOT_FOUND, f"cercat a: {places}")
