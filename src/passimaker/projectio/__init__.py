"""M12 · Save and open .passimaker project files (block B1).

A .passimaker file is indented UTF-8 JSON (§1.10: readable structured text):

    {"format": "passimaker", "format_version": 1, "project": {...}}

Every photo and song stores two paths: `path` (absolute) and `relative_path` (relative to the
folder of the .passimaker file, with "/" separators, or null when there is none, e.g. another drive).
On opening, the relative path is tried first, so a folder moved together with its photos, or a
USB stick with another drive letter, keeps working; then the absolute path.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, cast

from passimaker.common import PassiMakerError
from passimaker.model import defaults
from passimaker.model.editing import clamp_song
from passimaker.model.types import (
    Fade,
    FitMode,
    MotionMode,
    MotionType,
    Music,
    OutputFormat,
    Photo,
    PhotoMotion,
    Project,
    ResolvedFit,
    Rotation,
    Song,
    Window,
)

EXTENSION = ".passimaker"
FORMAT_NAME = "passimaker"
RECOVERY_FILE_NAME = "recuperacio" + EXTENSION

# Message keys (passimaker.i18n) of the errors raised by this module.
ERROR_READ = "projectio.read_error"
ERROR_WRITE = "projectio.write_error"
ERROR_CORRUPT = "projectio.corrupt"
ERROR_NEWER_VERSION = "projectio.newer_version"


class ProjectFileError(PassiMakerError):
    """Corrupt file, unknown newer format version, or I/O error."""


@dataclass(frozen=True, slots=True)
class OpenResult:
    project: Project
    missing_files: tuple[Path, ...]


# --- Saving ---------------------------------------------------------------------------------------


def _relative(path: Path, base: Path) -> str | None:
    try:
        return PurePosixPath(*Path(os.path.relpath(path, base)).parts).as_posix()
    except ValueError:  # different drive on Windows
        return None


def _absolute(path: Path) -> Path:
    return Path(os.path.normpath(path.absolute()))


def _window_to_json(window: Window) -> dict[str, Any]:
    return {"centre_x": window.centre_x, "centre_y": window.centre_y, "scale": window.scale}


def _motion_to_json(motion: PhotoMotion) -> dict[str, Any]:
    return {
        "mode": motion.mode.value,
        "type": motion.type.value,
        "draw_count": motion.draw_count,
        "start": _window_to_json(motion.start),
        "end": _window_to_json(motion.end),
        "resolved_fit": motion.resolved_fit.value,
    }


def _photo_to_json(photo: Photo, base: Path) -> dict[str, Any]:
    return {
        "id": photo.id,
        "path": str(_absolute(photo.path)),
        "relative_path": _relative(photo.path, base),
        "width": photo.width,
        "height": photo.height,
        "exif_orientation": photo.exif_orientation,
        "capture_time": None if photo.capture_time is None else photo.capture_time.isoformat(),
        "duration_s": photo.duration_s,
        "fit": photo.fit.value,
        "motion": _motion_to_json(photo.motion),
        "rotation": photo.rotation.value,
        "low_resolution": photo.low_resolution,
    }


def _fade_to_json(fade: Fade) -> dict[str, Any]:
    return {"enabled": fade.enabled, "seconds": fade.seconds}


def _song_to_json(song: Song, base: Path) -> dict[str, Any]:
    return {
        "id": song.id,
        "path": str(_absolute(song.path)),
        "relative_path": _relative(song.path, base),
        "original_duration_s": song.original_duration_s,
        "trim_start_s": song.trim_start_s,
        "trim_end_s": song.trim_end_s,
        "fade_in": _fade_to_json(song.fade_in),
        "fade_out": _fade_to_json(song.fade_out),
        "volume": song.volume,
        "loudness_gain_db": song.loudness_gain_db,
    }


def project_to_json(project: Project, base: Path) -> dict[str, Any]:
    """The JSON document of a project; relative paths are computed against `base`."""
    music = project.music
    return {
        "format": FORMAT_NAME,
        "format_version": defaults.FORMAT_VERSION,
        "project": {
            "name": project.name,
            "output_format": project.output_format.value,
            "seed": project.seed,
            "default_duration_s": project.default_duration_s,
            "crossfade_s": project.crossfade_s,
            "fade_from_black_s": project.fade_from_black_s,
            "fade_to_black_s": project.fade_to_black_s,
            "motion_enabled": project.motion_enabled,
            "zoom_amount": project.zoom_amount,
            "pan_amount": project.pan_amount,
            "photos": [_photo_to_json(p, base) for p in project.photos],
            "music": {
                "master_volume": music.master_volume,
                "normalize": music.normalize,
                "keep_fitted": music.keep_fitted,
                "songs": [_song_to_json(s, base) for s in music.songs],
            },
        },
    }


def _write_atomic(path: Path, text: str) -> None:
    """Writes to a temporary file in the same folder and renames it over `path`.

    If anything fails before the rename, the previous file is left untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _save(project: Project, path: Path, base: Path) -> None:
    try:
        text = json.dumps(project_to_json(project, base), ensure_ascii=False, indent=2, allow_nan=False)
        _write_atomic(path, text + "\n")
    except (OSError, ValueError) as error:
        raise ProjectFileError(ERROR_WRITE, f"{path}: {error}") from error


def save_project(project: Project, path: Path) -> None:
    """Atomic write (temporary file + rename). Stores relative and absolute paths."""
    path = _absolute(path)
    _save(project, path, path.parent)


# --- Opening --------------------------------------------------------------------------------------


class _CorruptError(Exception):
    """Internal: the document does not have the expected structure."""


def _field[T](data: Mapping[str, Any], key: str, kind: type[T] | tuple[type, ...]) -> T:
    if key not in data:
        raise _CorruptError(f"falta el camp {key!r}")
    value = data[key]
    if isinstance(value, bool) and kind in (int, float, (int, float)):
        raise _CorruptError(f"el camp {key!r} no és numèric")
    if not isinstance(value, kind):
        raise _CorruptError(f"el camp {key!r} té un tipus inesperat")
    return cast(T, value)


def _number(data: Mapping[str, Any], key: str) -> float:
    return float(_field(data, key, (int, float)))


def _optional_number(data: Mapping[str, Any], key: str) -> float | None:
    return None if data.get(key) is None else _number(data, key)


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _field(data, key, dict))


def _list(data: Mapping[str, Any], key: str) -> list[Any]:
    return cast(list[Any], _field(data, key, list))


def _enum[E: Enum](data: Mapping[str, Any], key: str, enum: type[E]) -> E:
    try:
        return enum(data[key])
    except (KeyError, ValueError) as error:
        raise _CorruptError(f"valor no vàlid al camp {key!r}") from error


def _window(data: Mapping[str, Any]) -> Window:
    return Window(_number(data, "centre_x"), _number(data, "centre_y"), _number(data, "scale"))


def _motion(data: Mapping[str, Any]) -> PhotoMotion:
    return PhotoMotion(
        mode=_enum(data, "mode", MotionMode),
        type=_enum(data, "type", MotionType),
        draw_count=_field(data, "draw_count", int),
        start=_window(_object(data, "start")),
        end=_window(_object(data, "end")),
        resolved_fit=_enum(data, "resolved_fit", ResolvedFit),
    )


@dataclass(frozen=True, slots=True)
class _Located:
    path: Path
    relative_path: Path | None
    found: bool


def _locate(data: Mapping[str, Any], base: Path) -> _Located:
    """Relative path first (moved folder, other drive letter), then the absolute one."""
    absolute = Path(_field(data, "path", str))
    stored = data.get("relative_path")
    if stored is not None and not isinstance(stored, str):
        raise _CorruptError("el camp 'relative_path' té un tipus inesperat")
    relative = None if stored is None else Path(*PurePosixPath(stored).parts)
    if relative is not None:
        candidate = Path(os.path.normpath(base / relative))
        if candidate.exists():
            return _Located(candidate, relative, True)
    return _Located(absolute, relative, absolute.exists())


def _capture_time(data: Mapping[str, Any]) -> datetime | None:
    value = data.get("capture_time")
    if value is None:
        return None
    try:
        return datetime.fromisoformat(_field(data, "capture_time", str))
    except ValueError as error:
        raise _CorruptError("data de captura no vàlida") from error


def _rotation(data: Mapping[str, Any]) -> Rotation:
    try:
        return Rotation(_field(data, "rotation", int))
    except ValueError as error:
        raise _CorruptError("gir no vàlid") from error


def _photo(data: Mapping[str, Any], base: Path, missing: list[Path]) -> Photo:
    located = _locate(data, base)
    if not located.found:
        missing.append(located.path)
    duration = _optional_number(data, "duration_s")
    return Photo(
        id=_field(data, "id", str),
        path=located.path,
        relative_path=located.relative_path,
        width=_field(data, "width", int),
        height=_field(data, "height", int),
        exif_orientation=_field(data, "exif_orientation", int),
        capture_time=_capture_time(data),
        duration_s=None if duration is None else defaults.PHOTO_DURATION_RANGE.clamp(duration),
        fit=_enum(data, "fit", FitMode),
        motion=_motion(_object(data, "motion")),
        rotation=_rotation(data),
        low_resolution=_field(data, "low_resolution", bool),
    )


def _fade(data: Mapping[str, Any]) -> Fade:
    return Fade(_field(data, "enabled", bool), defaults.SONG_FADE_RANGE.clamp(_number(data, "seconds")))


def _song(data: Mapping[str, Any], base: Path, missing: list[Path]) -> Song:
    located = _locate(data, base)
    if not located.found:
        missing.append(located.path)
    return clamp_song(
        Song(
            id=_field(data, "id", str),
            path=located.path,
            relative_path=located.relative_path,
            original_duration_s=_number(data, "original_duration_s"),
            trim_start_s=_number(data, "trim_start_s"),
            trim_end_s=_optional_number(data, "trim_end_s"),
            fade_in=_fade(_object(data, "fade_in")),
            fade_out=_fade(_object(data, "fade_out")),
            volume=_number(data, "volume"),
            loudness_gain_db=_optional_number(data, "loudness_gain_db"),
        )
    )


def _objects(data: Mapping[str, Any], key: str) -> Iterable[Mapping[str, Any]]:
    items = _list(data, key)
    for item in items:
        if not isinstance(item, dict):
            raise _CorruptError(f"element no vàlid a {key!r}")
    return cast(list[Mapping[str, Any]], items)


def project_from_json(document: object, base: Path) -> OpenResult:
    """Builds the project from a parsed document; relative paths are resolved against `base`.

    Values outside their ranges are clamped, as the controller would do.
    """
    if not isinstance(document, dict):
        raise ProjectFileError(ERROR_CORRUPT, "el document no és un objecte JSON")
    root = cast(Mapping[str, Any], document)
    try:
        if root.get("format") != FORMAT_NAME:
            raise _CorruptError("no és un projecte de PassiMaker")
        version = _field(root, "format_version", int)
        if version > defaults.FORMAT_VERSION:
            detail = f"versió del fitxer {version}, versió del programa {defaults.FORMAT_VERSION}"
            raise ProjectFileError(ERROR_NEWER_VERSION, detail)
        if version < 1:
            raise _CorruptError(f"versió no vàlida: {version}")
        data = _object(root, "project")
        music = _object(data, "music")
        missing: list[Path] = []
        photos = tuple(_photo(p, base, missing) for p in _objects(data, "photos"))
        songs = tuple(_song(s, base, missing) for s in _objects(music, "songs"))
        if len({p.id for p in photos}) != len(photos) or len({s.id for s in songs}) != len(songs):
            raise _CorruptError("identificadors repetits")
        if any(p.width <= 0 or p.height <= 0 for p in photos):
            raise _CorruptError("mida de foto no vàlida")
        project = Project(
            name=_field(data, "name", str),
            format_version=defaults.FORMAT_VERSION,
            output_format=_enum(data, "output_format", OutputFormat),
            seed=_field(data, "seed", int),
            default_duration_s=defaults.PHOTO_DURATION_RANGE.clamp(_number(data, "default_duration_s")),
            crossfade_s=defaults.CROSSFADE_RANGE.clamp(_number(data, "crossfade_s")),
            fade_from_black_s=defaults.BLACK_FADE_RANGE.clamp(_number(data, "fade_from_black_s")),
            fade_to_black_s=defaults.BLACK_FADE_RANGE.clamp(_number(data, "fade_to_black_s")),
            motion_enabled=_field(data, "motion_enabled", bool),
            zoom_amount=defaults.MOTION_AMOUNT_RANGE.clamp(_number(data, "zoom_amount")),
            pan_amount=defaults.MOTION_AMOUNT_RANGE.clamp(_number(data, "pan_amount")),
            photos=photos,
            music=Music(
                master_volume=defaults.MASTER_VOLUME_RANGE.clamp(_number(music, "master_volume")),
                normalize=_field(music, "normalize", bool),
                keep_fitted=_field(music, "keep_fitted", bool),
                songs=songs,
            ),
        )
    except _CorruptError as error:
        raise ProjectFileError(ERROR_CORRUPT, str(error)) from error
    return OpenResult(project, tuple(missing))


def _reject_constant(name: str) -> float:
    raise ValueError(f"valor no admès: {name}")


def _read_document(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ProjectFileError(ERROR_READ, f"{path}: {error}") from error
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as error:
        raise ProjectFileError(ERROR_CORRUPT, f"{path}: {error}") from error


def open_project(path: Path) -> OpenResult:
    """Reads a .passimaker file. Every problem with the file ends as a ProjectFileError."""
    path = _absolute(path)
    return project_from_json(_read_document(path), path.parent)


# --- Relinking ------------------------------------------------------------------------------------


def _index_by_name(folder: Path) -> dict[str, Path]:
    """File name (case-insensitive) → first path found, walking the folder in a stable order."""
    index: dict[str, Path] = {}
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            index.setdefault(name.casefold(), Path(root) / name)
    return index


def relink(project: Project, folder: Path) -> tuple[Project, int]:
    """Finds missing photos/songs by file name inside folder; returns (project, relinked count).

    Relinked items get relative_path=None: it is computed again when the project is saved.
    """
    index: dict[str, Path] | None = None
    count = 0

    def find(path: Path) -> Path | None:
        nonlocal index, count
        if path.exists():
            return None
        if index is None:
            index = _index_by_name(folder)
        found = index.get(path.name.casefold())
        if found is not None:
            count += 1
        return found

    def relinked[T: (Photo, Song)](item: T, finder: Callable[[Path], Path | None]) -> T:
        found = finder(item.path)
        return item if found is None else replace(item, path=found, relative_path=None)

    photos = tuple(relinked(p, find) for p in project.photos)
    songs = tuple(relinked(s, find) for s in project.music.songs)
    if count == 0:
        return project, 0
    return replace(project, photos=photos, music=replace(project.music, songs=songs)), count


# --- Recovery copy --------------------------------------------------------------------------------


def save_recovery(project: Project, recovery_dir: Path) -> Path:
    """Saves the recovery copy (§1.10: every 2 minutes, outside the project folder).

    Its relative paths are computed against the recovery folder, so only the absolute paths
    are meaningful when it is opened again.
    """
    path = _absolute(recovery_dir) / RECOVERY_FILE_NAME
    _save(project, path, path.parent)
    return path


def find_recovery(recovery_dir: Path) -> Path | None:
    path = recovery_dir / RECOVERY_FILE_NAME
    return path if path.is_file() else None


def clear_recovery(recovery_dir: Path) -> None:
    try:
        (recovery_dir / RECOVERY_FILE_NAME).unlink(missing_ok=True)
    except OSError as error:
        raise ProjectFileError(ERROR_WRITE, f"{recovery_dir}: {error}") from error
