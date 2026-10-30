"""Pure functions that apply each command to a project (block B1).

`apply_command` takes the current project and returns a new one; the controller adds the undo
history and the notifications on top. Values are clamped to the ranges in defaults.py, and
photo motions are kept consistent with the rest of the project:

- new and duplicated photos get a drawn motion (passimaker.motion.draw_motions);
- photos whose motion inputs change (size, fit, output format, visible duration or motion
  amounts) get their windows rebuilt with the same type (passimaker.motion.rebuild_motions);
- reordering never draws again (§1.5).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from itertools import pairwise
from typing import assert_never

from passimaker import timeline
from passimaker.model import defaults
from passimaker.model.commands import (
    AddBlackSlide,
    AddPhotos,
    AddSongs,
    Change,
    Command,
    DuplicatePhotos,
    FitToMusic,
    MovePhotos,
    MoveSongs,
    RemovePhotos,
    RemoveSongs,
    RerollMotions,
    RotatePhotos,
    SetDefaultDuration,
    SetMusicSettings,
    SetPhotoDuration,
    SetPhotoFit,
    SetPhotoMotion,
    SetProjectSettings,
    SortPhotos,
    UpdateSong,
)
from passimaker.model.types import (
    BlackSlide,
    BlackSlidePosition,
    Fade,
    MotionMode,
    Music,
    Photo,
    PhotoMotion,
    Project,
    Rotation,
    Song,
)
from passimaker.motion import (
    INTENSITY_PRESETS,
    MotionAmounts,
    MotionRequest,
    draw_motions,
    rebuild_motions,
    resolve_fit,
)

# --- Derived values -------------------------------------------------------------------------------


def visible_durations(project: Project) -> list[float]:
    """Time each photo is on screen: its duration plus half of each neighbouring crossfade.

    A crossfade never lasts more than half of the shorter of its two photos (§1.4). This is the
    same rule passimaker.timeline applies (block B2); the motion draw only needs the durations.
    The black slides are neighbours like any photo (M08) but get no value: one value per photo.
    """
    durations = [project.photo_duration(s) for s in project.slides]
    halves = [min(project.crossfade_s, a / 2, b / 2) / 2 for a, b in pairwise(durations)]
    visible = [
        d + (halves[i - 1] if i > 0 else 0.0) + (halves[i] if i < len(halves) else 0.0)
        for i, d in enumerate(durations)
    ]
    return [v for v, s in zip(visible, project.slides, strict=True) if isinstance(s, Photo)]


def song_duration(song: Song) -> float:
    """Duration of a song after its trims."""
    end = song.original_duration_s if song.trim_end_s is None else song.trim_end_s
    return max(0.0, end - song.trim_start_s)


def music_duration(music: Music) -> float:
    return sum(song_duration(s) for s in music.songs)


def changes_between(old: Project, new: Project) -> set[Change]:
    """Kinds of data that differ between two versions of the project (SAVED_STATE excluded)."""
    if old is new:
        return set()
    checks: list[tuple[Change, Callable[[Project], Hashable]]] = [
        (Change.PHOTOS, _photo_identity),
        (Change.TIMING, _timing_key),
        (Change.MOTION, _motion_key),
        (Change.MUSIC, lambda p: p.music),
        (Change.SETTINGS, lambda p: (p.name, p.seed, p.format_version)),
    ]
    return {change for change, key in checks if key(old) != key(new)}


def _photo_identity(project: Project) -> Hashable:
    return tuple(
        (s.id, s.path, s.relative_path, s.exif_orientation, s.capture_time, s.low_resolution)
        if isinstance(s, Photo)
        else (s.id,)
        for s in project.slides
    )


def _timing_key(project: Project) -> Hashable:
    return (
        project.default_duration_s,
        project.crossfade_s,
        project.fade_from_black_s,
        project.fade_to_black_s,
        tuple(s.duration_s for s in project.slides),
    )


def _motion_key(project: Project) -> Hashable:
    return (
        project.output_format,
        project.motion_enabled,
        project.zoom_amount,
        project.pan_amount,
        tuple((p.width, p.height, p.fit, p.rotation, p.motion) for p in project.photos),
    )


# --- Clamping -------------------------------------------------------------------------------------


def _clamp_duration(seconds: float | None) -> float | None:
    return None if seconds is None else defaults.PHOTO_DURATION_RANGE.clamp(seconds)


def _clamp_fade(fade: Fade) -> Fade:
    return Fade(fade.enabled, defaults.SONG_FADE_RANGE.clamp(fade.seconds))


def clamp_song(song: Song) -> Song:
    """Song settings inside their ranges; the trim end is never before the trim start."""
    original = max(0.0, song.original_duration_s)
    start = min(original, max(0.0, song.trim_start_s))
    end = None if song.trim_end_s is None else min(original, max(start, song.trim_end_s))
    return replace(
        song,
        trim_start_s=start,
        trim_end_s=end,
        fade_in=_clamp_fade(song.fade_in),
        fade_out=_clamp_fade(song.fade_out),
        volume=defaults.SONG_VOLUME_RANGE.clamp(song.volume),
    )


# --- Identifiers and ordering ---------------------------------------------------------------------


def unique_id(wanted: str, taken: set[str]) -> str:
    """`wanted` if free, else `wanted~2`, `wanted~3`... Deterministic, so motions stay reproducible."""
    if wanted not in taken:
        return wanted
    n = 2
    while f"{wanted}~{n}" in taken:
        n += 1
    return f"{wanted}~{n}"


def natural_key(name: str) -> tuple[str | int, ...]:
    """Natural order: "IMG_2" before "IMG_10"; case-insensitive."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name.casefold()))


def _date_key(photo: Photo) -> tuple[bool, datetime, tuple[str | int, ...]]:
    when = photo.capture_time.replace(tzinfo=None) if photo.capture_time is not None else datetime.min
    return (photo.capture_time is None, when, natural_key(photo.path.name))


def _insert[T](items: Sequence[T], new: Sequence[T], index: int | None) -> tuple[T, ...]:
    at = len(items) if index is None else min(len(items), max(0, index))
    return (*items[:at], *new, *items[at:])


def _move_block[T](
    items: Sequence[T], key: Callable[[T], str], ids: Iterable[str], target: int
) -> tuple[T, ...]:
    """Moves the given items, in their current order, to `target` (an index in the list before the move)."""
    chosen = set(ids)
    target = min(len(items), max(0, target))
    moving = [x for x in items if key(x) in chosen]
    rest = [x for x in items if key(x) not in chosen]
    position = target - sum(1 for x in items[:target] if key(x) in chosen)
    return (*rest[:position], *moving, *rest[position:])


# --- Motions --------------------------------------------------------------------------------------


def _amounts(project: Project) -> MotionAmounts:
    return MotionAmounts(project.zoom_amount, project.pan_amount)


def _requests(project: Project, current: Mapping[str, PhotoMotion | None]) -> list[MotionRequest]:
    """One request per photo; `current` overrides the photo's own motion (None = never drawn)."""
    visible = visible_durations(project)
    return [
        MotionRequest(
            photo_id=p.id,
            width=p.width,
            height=p.height,
            visible_duration_s=visible[i],
            fit=resolve_fit(p.width, p.height, project.output_format, p.fit),
            output_format=project.output_format,
            mode=p.motion.mode,
            manual_type=p.motion.type if p.motion.mode is MotionMode.MANUAL else None,
            draw_count=p.motion.draw_count,
            current=current.get(p.id, p.motion),
        )
        for i, p in enumerate(project.photos)
    ]


def _with_photos(project: Project, photos: Iterable[Photo]) -> Project:
    """The project with these photos between its black slides, which never move (M08)."""
    start = () if project.black_start is None else (project.black_start,)
    end = () if project.black_end is None else (project.black_end,)
    return replace(project, slides=(*start, *photos, *end))


def _with_motions(project: Project, motions: Mapping[str, PhotoMotion]) -> Project:
    if not motions:
        return project
    return _with_photos(
        project, (replace(p, motion=motions[p.id]) if p.id in motions else p for p in project.photos)
    )


def _draw(project: Project, current: Mapping[str, PhotoMotion | None], reroll: bool) -> Project:
    """Draws the motion of the photos in `current` (the other photos act as neighbours).

    reroll=True: the new automatic motion differs from the given current one ("draw again",
    duplicate). reroll=False: photos given with current=None get a first draw.
    """
    if not current:
        return project
    ids = frozenset(current)
    which = ids if reroll else frozenset[str]()
    drawn = draw_motions(_requests(project, current), project.seed, _amounts(project), which)
    return _with_motions(project, {pid: drawn[pid] for pid in ids})


def _motion_inputs(project: Project) -> dict[str, Hashable]:
    visible = visible_durations(project)
    shared = (project.output_format, project.zoom_amount, project.pan_amount)
    return {p.id: (p.width, p.height, p.fit, visible[i], shared) for i, p in enumerate(project.photos)}


def _refresh_motions(old: Project, new: Project, skip: Iterable[str] = ()) -> Project:
    """Rebuilds (same type, new windows) the motion of photos whose inputs changed."""
    before = _motion_inputs(old)
    skipped = set(skip)
    stale = {pid for pid, key in _motion_inputs(new).items() if pid not in skipped and before.get(pid) != key}
    if not stale:
        return new
    rebuilt = rebuild_motions(_requests(new, {}), new.seed, _amounts(new))
    return _with_motions(new, {pid: rebuilt[pid] for pid in stale})


# --- Fit to music ---------------------------------------------------------------------------------


def fit_to_music(project: Project) -> Project:
    """Rescales the photo durations so the show lasts as long as the music (§1.7).

    The durations come from passimaker.timeline.fit_to_music (block B2), which keeps the proportions
    and applies the 1-3 s limits. Photos that used the default duration keep doing so (with a new
    default) when they all get the same fitted value, so the "custom duration" marks do not change.
    """
    # M08: the black slides keep their own duration; the photos share the rest of the music.
    target = music_duration(project.music) - sum(
        s.duration_s for s in project.slides if isinstance(s, BlackSlide)
    )
    if not project.photos or target <= 0:
        return project
    durations = [project.photo_duration(p) for p in project.photos]
    result = timeline.fit_to_music(durations, target)
    fitted = [defaults.FIT_TO_MUSIC_DURATION_RANGE.clamp(d) for d in result.durations]
    default_values = {fitted[i] for i, p in enumerate(project.photos) if p.duration_s is None}
    new_default = default_values.pop() if len(default_values) == 1 else None
    photos = tuple(
        replace(p, duration_s=None if (p.duration_s is None and new_default is not None) else fitted[i])
        for i, p in enumerate(project.photos)
    )
    default = new_default if new_default is not None else project.default_duration_s
    return replace(_with_photos(project, photos), default_duration_s=default)


def _fitted(project: Project) -> Project:
    """fit_to_music plus the motion rebuild that the new durations require."""
    return _refresh_motions(project, fit_to_music(project))


def _keep_fitted(project: Project) -> Project:
    """Fits again after adding or removing photos or songs when "keep fitted" is on (§1.7)."""
    if project.music.keep_fitted and project.music.songs and project.photos:
        return _fitted(project)
    return project


# --- Commands -------------------------------------------------------------------------------------


def _add_photos(project: Project, command: AddPhotos) -> Project:
    taken = {s.id for s in project.slides}
    new: list[Photo] = []
    for photo in command.photos:
        pid = unique_id(photo.id, taken)
        taken.add(pid)
        new.append(replace(photo, id=pid, duration_s=_clamp_duration(photo.duration_s)))
    edited = _with_photos(project, _insert(project.photos, new, command.index))
    edited = _refresh_motions(project, edited, skip=(p.id for p in new))
    edited = _draw(edited, {p.id: None for p in new}, reroll=False)
    return _keep_fitted(edited)


def _remove_photos(project: Project, command: RemovePhotos) -> Project:
    slides = tuple(s for s in project.slides if s.id not in command.photo_ids)
    edited = _refresh_motions(project, replace(project, slides=slides))
    return _keep_fitted(edited)


def _move_photos(project: Project, command: MovePhotos) -> Project:
    photos = _move_block(project.photos, lambda p: p.id, command.photo_ids, command.target_index)
    return _refresh_motions(project, _with_photos(project, photos))


def _duplicate_photos(project: Project, command: DuplicatePhotos) -> Project:
    chosen = set(command.photo_ids)
    taken = {s.id for s in project.slides}
    photos: list[Photo] = []
    originals: dict[str, PhotoMotion] = {}
    for photo in project.photos:
        photos.append(photo)
        if photo.id in chosen:
            copy_id = unique_id(photo.id, taken)
            taken.add(copy_id)
            photos.append(replace(photo, id=copy_id, motion=replace(photo.motion, draw_count=0)))
            originals[copy_id] = photo.motion
    edited = _with_photos(project, photos)
    edited = _refresh_motions(project, edited, skip=originals)
    # The copy keeps duration and fit but gets a new motion, different from the original's.
    edited = _draw(edited, dict(originals), reroll=True)
    return _keep_fitted(edited)


def _sort_photos(project: Project, command: SortPhotos) -> Project:
    if command.by_date:
        photos = sorted(project.photos, key=_date_key)
    else:
        photos = sorted(project.photos, key=lambda p: natural_key(p.path.name))
    return _refresh_motions(project, _with_photos(project, photos))


def _set_default_duration(project: Project, command: SetDefaultDuration) -> Project:
    seconds = defaults.PHOTO_DURATION_RANGE.clamp(command.seconds)
    return _refresh_motions(project, replace(project, default_duration_s=seconds))


def _map_photos(project: Project, ids: Iterable[str], change: Callable[[Photo], Photo]) -> Project:
    chosen = set(ids)
    return _with_photos(project, (change(p) if p.id in chosen else p for p in project.photos))


def _set_photo_duration(project: Project, command: SetPhotoDuration) -> Project:
    seconds = _clamp_duration(command.seconds)
    black = defaults.BLACK_SLIDE_DURATION_S if seconds is None else seconds
    slides = tuple(
        s
        if s.id not in command.photo_ids
        else replace(s, duration_s=black)
        if isinstance(s, BlackSlide)
        else replace(s, duration_s=seconds)
        for s in project.slides
    )
    return _refresh_motions(project, replace(project, slides=slides))


def _add_black_slide(project: Project, command: AddBlackSlide) -> Project:
    slide = BlackSlide(command.position)
    if command.position is BlackSlidePosition.START:
        if project.black_start is not None:
            return project
        slides = (slide, *project.slides)
    else:
        if project.black_end is not None:
            return project
        slides = (*project.slides, slide)
    return _keep_fitted(_refresh_motions(project, replace(project, slides=slides)))


def _set_photo_fit(project: Project, command: SetPhotoFit) -> Project:
    edited = _map_photos(project, command.photo_ids, lambda p: replace(p, fit=command.fit))
    return _refresh_motions(project, edited)


def _set_photo_motion(project: Project, command: SetPhotoMotion) -> Project:
    ids = [p.id for p in project.photos if p.id in command.photo_ids]
    if command.motion_type is None:
        # Back to automatic mode: a fresh automatic draw.
        template = PhotoMotion(mode=MotionMode.AUTO)
    else:
        template = PhotoMotion(mode=MotionMode.MANUAL, type=command.motion_type)
    edited = _map_photos(
        project, ids, lambda p: replace(p, motion=replace(template, draw_count=p.motion.draw_count))
    )
    return _draw(edited, dict.fromkeys(ids), reroll=False)


def _reroll_motions(project: Project, command: RerollMotions) -> Project:
    if command.photo_ids is None:
        ids = [p.id for p in project.photos if p.motion.mode is MotionMode.AUTO]
    else:
        ids = [p.id for p in project.photos if p.id in command.photo_ids]
    # The draw count goes up first, so the new draw differs from the previous one (B3 note). A photo whose
    # motion was fixed by hand goes back to automatic mode: one command, one undo step.
    edited = _map_photos(
        project,
        ids,
        lambda p: replace(
            p, motion=replace(p.motion, mode=MotionMode.AUTO, draw_count=p.motion.draw_count + 1)
        ),
    )
    chosen = set(ids)
    return _draw(edited, {p.id: p.motion for p in edited.photos if p.id in chosen}, reroll=True)


def _rotate(photo: Photo, rotation: Rotation) -> Photo:
    turned = Rotation((photo.rotation.value + rotation.value) % 360)
    swap = rotation in (Rotation.R90, Rotation.R270)
    width, height = (photo.height, photo.width) if swap else (photo.width, photo.height)
    return replace(photo, rotation=turned, width=width, height=height)


def _rotate_photos(project: Project, command: RotatePhotos) -> Project:
    edited = _map_photos(project, command.photo_ids, lambda p: _rotate(p, command.rotation))
    return _refresh_motions(project, edited)


def _set_project_settings(project: Project, command: SetProjectSettings) -> Project:
    edited = project
    if command.name is not None:
        edited = replace(edited, name=command.name)
    if command.output_format is not None:
        edited = replace(edited, output_format=command.output_format)
    if command.crossfade_s is not None:
        edited = replace(edited, crossfade_s=defaults.CROSSFADE_RANGE.clamp(command.crossfade_s))
    if command.fade_from_black_s is not None:
        edited = replace(edited, fade_from_black_s=defaults.BLACK_FADE_RANGE.clamp(command.fade_from_black_s))
    if command.fade_to_black_s is not None:
        edited = replace(edited, fade_to_black_s=defaults.BLACK_FADE_RANGE.clamp(command.fade_to_black_s))
    if command.motion_enabled is not None:
        edited = replace(edited, motion_enabled=command.motion_enabled)
    if command.intensity is not None:
        preset = INTENSITY_PRESETS[command.intensity]
        edited = replace(edited, zoom_amount=preset.zoom, pan_amount=preset.pan)
    if command.zoom_amount is not None:
        edited = replace(edited, zoom_amount=defaults.MOTION_AMOUNT_RANGE.clamp(command.zoom_amount))
    if command.pan_amount is not None:
        edited = replace(edited, pan_amount=defaults.MOTION_AMOUNT_RANGE.clamp(command.pan_amount))
    return _refresh_motions(project, edited)


def _with_songs(project: Project, songs: Sequence[Song]) -> Project:
    return replace(project, music=replace(project.music, songs=tuple(songs)))


def _add_songs(project: Project, command: AddSongs) -> Project:
    taken = {s.id for s in project.music.songs}
    new: list[Song] = []
    for song in command.songs:
        sid = unique_id(song.id, taken)
        taken.add(sid)
        new.append(clamp_song(replace(song, id=sid)))
    return _keep_fitted(_with_songs(project, _insert(project.music.songs, new, command.index)))


def _remove_songs(project: Project, command: RemoveSongs) -> Project:
    songs = [s for s in project.music.songs if s.id not in command.song_ids]
    return _keep_fitted(_with_songs(project, songs))


def _move_songs(project: Project, command: MoveSongs) -> Project:
    return _with_songs(
        project, _move_block(project.music.songs, lambda s: s.id, command.song_ids, command.target_index)
    )


def _update_song(project: Project, command: UpdateSong) -> Project:
    song = clamp_song(command.song)
    songs = [song if s.id == song.id else s for s in project.music.songs]
    return _keep_fitted(_with_songs(project, songs))


def _set_music_settings(project: Project, command: SetMusicSettings) -> Project:
    music = project.music
    if command.master_volume is not None:
        music = replace(music, master_volume=defaults.MASTER_VOLUME_RANGE.clamp(command.master_volume))
    if command.normalize is not None:
        music = replace(music, normalize=command.normalize)
    if command.keep_fitted is not None:
        music = replace(music, keep_fitted=command.keep_fitted)
    edited = replace(project, music=music)
    if command.keep_fitted and not project.music.keep_fitted:
        edited = _keep_fitted(edited)
    return edited


def apply_command(project: Project, command: Command) -> Project:
    """The project after applying `command` (the same object if nothing applies)."""
    match command:
        case AddPhotos():
            edited = _add_photos(project, command)
        case RemovePhotos():
            edited = _remove_photos(project, command)
        case MovePhotos():
            edited = _move_photos(project, command)
        case DuplicatePhotos():
            edited = _duplicate_photos(project, command)
        case SortPhotos():
            edited = _sort_photos(project, command)
        case AddBlackSlide():
            edited = _add_black_slide(project, command)
        case SetDefaultDuration():
            edited = _set_default_duration(project, command)
        case SetPhotoDuration():
            edited = _set_photo_duration(project, command)
        case SetPhotoFit():
            edited = _set_photo_fit(project, command)
        case SetPhotoMotion():
            edited = _set_photo_motion(project, command)
        case RerollMotions():
            edited = _reroll_motions(project, command)
        case RotatePhotos():
            edited = _rotate_photos(project, command)
        case SetProjectSettings():
            edited = _set_project_settings(project, command)
        case AddSongs():
            edited = _add_songs(project, command)
        case RemoveSongs():
            edited = _remove_songs(project, command)
        case MoveSongs():
            edited = _move_songs(project, command)
        case UpdateSong():
            edited = _update_song(project, command)
        case SetMusicSettings():
            edited = _set_music_settings(project, command)
        case FitToMusic():
            edited = _fitted(project)
        case _:
            assert_never(command)
    return project if edited == project else edited
