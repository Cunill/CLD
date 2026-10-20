"""B1: .passimaker files (save/open round trip, relative paths, relinking, safe writing, recovery)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from passimaker import projectio
from passimaker.model import defaults
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
from passimaker.projectio import (
    ERROR_CORRUPT,
    ERROR_NEWER_VERSION,
    ProjectFileError,
    clear_recovery,
    find_recovery,
    open_project,
    relink,
    save_project,
    save_recovery,
)

# --- Strategies -----------------------------------------------------------------------------------

NAME_CHARS = "abcdefxyzABCàèéíïòóúüçñÀÉÇ·'_-0123456789"
names = st.text(NAME_CHARS, min_size=1, max_size=12)
folders = st.lists(names, max_size=2).map(lambda parts: Path(*parts) if parts else Path())
unit = st.floats(0.0, 1.0, allow_nan=False)
finite = st.floats(-1e6, 1e6, allow_nan=False)


def in_range(r: defaults.Range) -> st.SearchStrategy[float]:
    return st.floats(r.minimum, r.maximum, allow_nan=False)


windows = st.builds(Window, unit, unit, st.floats(0.5, 4.0))
motions = st.builds(
    PhotoMotion,
    st.sampled_from(MotionMode),
    st.sampled_from(MotionType),
    st.integers(0, 1000),
    windows,
    windows,
    st.sampled_from(ResolvedFit),
)
zones = st.sampled_from([None, UTC, timezone(timedelta(hours=2)), timezone(timedelta(hours=-5, minutes=-30))])
capture_times = st.none() | st.builds(
    lambda when, zone: when.replace(tzinfo=zone),
    st.datetimes(datetime(1990, 1, 1), datetime(2040, 1, 1)),
    zones,
)


@st.composite
def located_paths(draw: st.DrawFn, base: Path, extension: str) -> tuple[Path, Path]:
    """A file inside the project folder, or next to it (relative path with "..")."""
    outside = draw(st.booleans())
    folder = (base.parent / "fora") if outside else base
    path = folder / draw(folders) / f"{draw(names)}{extension}"
    return path, Path(os.path.relpath(path, base))


@st.composite
def photos_strategy(draw: st.DrawFn, base: Path, pid: str) -> Photo:
    path, relative = draw(located_paths(base, ".jpg"))
    return Photo(
        id=pid,
        path=path,
        relative_path=relative,
        width=draw(st.integers(1, 20000)),
        height=draw(st.integers(1, 20000)),
        exif_orientation=draw(st.integers(1, 8)),
        capture_time=draw(capture_times),
        duration_s=draw(st.none() | in_range(defaults.PHOTO_DURATION_RANGE)),
        fit=draw(st.sampled_from(FitMode)),
        motion=draw(motions),
        rotation=draw(st.sampled_from(Rotation)),
        low_resolution=draw(st.booleans()),
    )


fades = st.builds(Fade, st.booleans(), in_range(defaults.SONG_FADE_RANGE))


@st.composite
def songs_strategy(draw: st.DrawFn, base: Path, sid: str) -> Song:
    path, relative = draw(located_paths(base, ".mp3"))
    length = draw(st.floats(0.0, 7200.0))
    start = draw(st.floats(0.0, 1.0)) * length
    end = draw(st.none() | st.floats(0.0, 1.0).map(lambda f: min(length, start + f * (length - start))))
    return Song(
        id=sid,
        path=path,
        relative_path=relative,
        original_duration_s=length,
        trim_start_s=start,
        trim_end_s=end,
        fade_in=draw(fades),
        fade_out=draw(fades),
        volume=draw(in_range(defaults.SONG_VOLUME_RANGE)),
        loudness_gain_db=draw(st.none() | finite),
    )


@st.composite
def projects(draw: st.DrawFn, base: Path) -> Project:
    photo_count = draw(st.integers(0, 6))
    song_count = draw(st.integers(0, 3))
    return Project(
        name=draw(st.text(max_size=30)),
        output_format=draw(st.sampled_from(OutputFormat)),
        seed=draw(st.integers(0, 2**63)),
        default_duration_s=draw(in_range(defaults.PHOTO_DURATION_RANGE)),
        crossfade_s=draw(in_range(defaults.CROSSFADE_RANGE)),
        fade_from_black_s=draw(in_range(defaults.BLACK_FADE_RANGE)),
        fade_to_black_s=draw(in_range(defaults.BLACK_FADE_RANGE)),
        motion_enabled=draw(st.booleans()),
        zoom_amount=draw(in_range(defaults.MOTION_AMOUNT_RANGE)),
        pan_amount=draw(in_range(defaults.MOTION_AMOUNT_RANGE)),
        photos=tuple(draw(photos_strategy(base, f"foto-{i}")) for i in range(photo_count)),
        music=Music(
            master_volume=draw(in_range(defaults.MASTER_VOLUME_RANGE)),
            normalize=draw(st.booleans()),
            keep_fitted=draw(st.booleans()),
            songs=tuple(draw(songs_strategy(base, f"cançó-{i}")) for i in range(song_count)),
        ),
    )


ROUND_TRIP_BASE = Path(tempfile.gettempdir()).resolve() / "passimaker-proves" / "Projectes d'estiu àèç"


@settings(max_examples=200, deadline=None)
@given(projects(ROUND_TRIP_BASE))
def test_save_and_open_give_an_identical_project(project: Project) -> None:
    path = ROUND_TRIP_BASE / "Viatge a Girona·ñ.passimaker"
    save_project(project, path)
    result = open_project(path)
    assert result.project == project
    expected_missing = [p.path for p in project.photos] + [s.path for s in project.music.songs]
    assert list(result.missing_files) == expected_missing


@pytest.fixture(autouse=True, scope="module")
def _clean_round_trip_folder() -> object:
    yield
    shutil.rmtree(ROUND_TRIP_BASE.parent, ignore_errors=True)


# --- Real files -----------------------------------------------------------------------------------


def make_files(folder: Path, names: list[str]) -> list[Path]:
    paths: list[Path] = []
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        paths.append(path)
    return paths


def simple_project(photo_paths: list[Path], song_paths: list[Path] = ()) -> Project:  # type: ignore[assignment]
    return Project(
        name="prova",
        photos=tuple(Photo(f"p{i}", p, None, 4000, 3000) for i, p in enumerate(photo_paths)),
        music=Music(songs=tuple(Song(f"s{i}", p, None, 120.0) for i, p in enumerate(song_paths))),
    )


def test_file_is_readable_indented_json_with_a_version(tmp_path: Path) -> None:
    path = tmp_path / "p.passimaker"
    save_project(simple_project([tmp_path / "fotos" / "Càmping.jpg"]), path)
    text = path.read_text(encoding="utf-8")
    assert "\n  " in text and "Càmping.jpg" in text  # indented, accents kept as text
    document = json.loads(text)
    assert document["format"] == "passimaker" and document["format_version"] == defaults.FORMAT_VERSION
    photo_data = document["project"]["photos"][0]
    assert photo_data["relative_path"] == "fotos/Càmping.jpg"
    assert Path(photo_data["path"]).is_absolute()


def test_moving_the_whole_folder_keeps_everything(tmp_path: Path) -> None:
    original = tmp_path / "Disc E" / "Passi d'estiu"
    photo_paths = make_files(original, ["fotos/IMG_1.jpg", "fotos/sub/àvia.jpg"])
    song_paths = make_files(original, ["música/cançó.mp3"])
    save_project(simple_project(photo_paths, song_paths), original / "estiu.passimaker")

    moved = tmp_path / "Disc F" / "còpia"
    moved.parent.mkdir()
    shutil.move(original, moved)
    result = open_project(moved / "estiu.passimaker")
    assert result.missing_files == ()
    assert [p.path for p in result.project.photos] == [
        moved / "fotos/IMG_1.jpg",
        moved / "fotos/sub/àvia.jpg",
    ]
    assert result.project.music.songs[0].path == moved / "música/cançó.mp3"


def test_absolute_path_is_used_when_only_the_project_file_moves(tmp_path: Path) -> None:
    photo_paths = make_files(tmp_path / "fotos", ["a.jpg"])
    save_project(simple_project(photo_paths), tmp_path / "projectes" / "p.passimaker")
    (tmp_path / "projectes" / "p.passimaker").rename(tmp_path / "p.passimaker")
    result = open_project(tmp_path / "p.passimaker")
    assert result.missing_files == ()
    assert result.project.photos[0].path == photo_paths[0]


def test_missing_files_are_listed_and_relinked_by_name(tmp_path: Path) -> None:
    photo_paths = make_files(tmp_path / "vell", ["a.jpg", "B.JPG", "c.jpg"])
    song_paths = make_files(tmp_path / "vell", ["tema.mp3"])
    save_project(simple_project(photo_paths, song_paths), tmp_path / "projecte" / "p.passimaker")
    shutil.rmtree(tmp_path / "vell")
    make_files(tmp_path / "nou", ["sub/a.jpg", "b.jpg", "tema.mp3"])  # c.jpg is lost

    result = open_project(tmp_path / "projecte" / "p.passimaker")
    assert set(result.missing_files) == {*photo_paths, *song_paths}
    project, count = relink(result.project, tmp_path / "nou")
    assert count == 3
    paths = [p.path for p in project.photos]
    assert paths == [tmp_path / "nou/sub/a.jpg", tmp_path / "nou/b.jpg", photo_paths[2]]
    assert project.music.songs[0].path == tmp_path / "nou/tema.mp3"
    assert project.photos[0].relative_path is None

    save_project(project, tmp_path / "projecte" / "p.passimaker")
    reopened = open_project(tmp_path / "projecte" / "p.passimaker")
    assert reopened.missing_files == (photo_paths[2],)


def test_relink_with_nothing_missing_returns_the_same_project(tmp_path: Path) -> None:
    project = simple_project(make_files(tmp_path, ["a.jpg"]))
    assert relink(project, tmp_path) == (project, 0)


# --- Safe writing ---------------------------------------------------------------------------------


@pytest.mark.parametrize("failing", ["fsync", "replace"])
def test_a_failure_while_saving_leaves_the_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    path = tmp_path / "p.passimaker"
    save_project(Project(name="primer"), path)
    before = path.read_bytes()

    def crash(*_args: object) -> None:
        raise OSError("disc ple")

    if failing == "fsync":
        monkeypatch.setattr(projectio.os, "fsync", crash)
    else:
        monkeypatch.setattr(Path, "replace", crash)
    with pytest.raises(ProjectFileError):
        save_project(Project(name="segon"), path)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["p.passimaker"]  # no temporary files left
    assert open_project(path).project.name == "primer"


def test_an_interrupted_save_does_not_reach_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "p.passimaker"
    save_project(Project(name="primer"), path)
    monkeypatch.setattr(projectio.os, "fsync", lambda _fd: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        save_project(Project(name="segon"), path)
    assert open_project(path).project.name == "primer"
    assert len(list(tmp_path.iterdir())) == 1


def test_save_creates_the_folder(tmp_path: Path) -> None:
    path = tmp_path / "nova carpeta" / "p.passimaker"
    save_project(Project(), path)
    assert open_project(path).project == Project()


# --- Controlled errors ----------------------------------------------------------------------------


def write(tmp_path: Path, content: str | bytes) -> Path:
    path = tmp_path / "p.passimaker"
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def valid_document(tmp_path: Path) -> dict[str, object]:
    path = tmp_path / "valid.passimaker"
    save_project(simple_project([tmp_path / "a.jpg"], [tmp_path / "s.mp3"]), path)
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_newer_version_gives_a_clear_error(tmp_path: Path) -> None:
    document = valid_document(tmp_path)
    document["format_version"] = defaults.FORMAT_VERSION + 1
    with pytest.raises(ProjectFileError) as error:
        open_project(write(tmp_path, json.dumps(document)))
    assert error.value.message_key == ERROR_NEWER_VERSION


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{",
        "[]",
        "null",
        '{"format": "altre", "format_version": 1}',
        '{"format": "passimaker"}',
        '{"format": "passimaker", "format_version": "1", "project": {}}',
        '{"format": "passimaker", "format_version": 0, "project": {}}',
        '{"format": "passimaker", "format_version": 1, "project": {}}',
        '{"format": "passimaker", "format_version": 1, "project": NaN}',
        "[" * 100_000,
        b"\xff\xfe\x00garbage",
    ],
    # Short ids: pytest copies the test id to PYTEST_CURRENT_TEST, limited to 32,767 characters on Windows.
    ids=lambda content: f"len{len(content)}",
)
def test_corrupt_files_give_a_controlled_error(tmp_path: Path, content: str | bytes) -> None:
    with pytest.raises(ProjectFileError):
        open_project(write(tmp_path, content))


def _mutations() -> list[tuple[str, object]]:
    return [
        ("project.photos.0.width", "ample"),
        ("project.photos.0.width", 0),
        ("project.photos.0.width", True),
        ("project.photos.0.fit", "estirar"),
        ("project.photos.0.rotation", 45),
        ("project.photos.0.capture_time", "ahir"),
        ("project.photos.0.motion.start", None),
        ("project.photos.0.motion.draw_count", 1.5),
        ("project.photos.0.relative_path", 3),
        ("project.photos.0", "foto"),
        ("project.photos", {}),
        ("project.music.songs.0.volume", "fort"),
        ("project.music.songs.0.fade_in", [1, 2]),
        ("project.music", None),
        ("project.output_format", "quadrat"),
        ("project.seed", "llavor"),
        ("project.name", 5),
    ]


@pytest.mark.parametrize(("where", "value"), _mutations())
def test_wrong_fields_give_a_controlled_error(tmp_path: Path, where: str, value: object) -> None:
    document = valid_document(tmp_path)
    target: object = document
    *parents, last = where.split(".")
    for part in parents:
        target = target[int(part)] if isinstance(target, list) else target[part]  # type: ignore[index]
    if isinstance(target, list):
        target[int(last)] = value
    else:
        target[last] = value  # type: ignore[index]
    with pytest.raises(ProjectFileError) as error:
        open_project(write(tmp_path, json.dumps(document)))
    assert error.value.message_key == ERROR_CORRUPT


def test_repeated_ids_are_rejected(tmp_path: Path) -> None:
    document = valid_document(tmp_path)
    photos = document["project"]["photos"]  # type: ignore[index]
    photos.append(dict(photos[0]))  # type: ignore[union-attr]
    with pytest.raises(ProjectFileError):
        open_project(write(tmp_path, json.dumps(document)))


def test_out_of_range_values_are_clamped_on_open(tmp_path: Path) -> None:
    document = valid_document(tmp_path)
    data = document["project"]
    data["crossfade_s"] = 30  # type: ignore[index]
    data["photos"][0]["duration_s"] = 0.01  # type: ignore[index]
    data["music"]["songs"][0]["volume"] = 7  # type: ignore[index]
    project = open_project(write(tmp_path, json.dumps(document))).project
    assert project.crossfade_s == defaults.CROSSFADE_RANGE.maximum
    assert project.photos[0].duration_s == defaults.PHOTO_DURATION_RANGE.minimum
    assert project.music.songs[0].volume == defaults.SONG_VOLUME_RANGE.maximum


def test_unreadable_or_missing_file_gives_a_controlled_error(tmp_path: Path) -> None:
    with pytest.raises(ProjectFileError):
        open_project(tmp_path / "no existeix.passimaker")
    with pytest.raises(ProjectFileError):
        open_project(tmp_path)  # a folder


def test_values_that_json_cannot_store_give_a_controlled_error(tmp_path: Path) -> None:
    with pytest.raises(ProjectFileError):
        save_project(Project(zoom_amount=float("nan")), tmp_path / "p.passimaker")
    assert not list(tmp_path.iterdir())


# --- Recovery -------------------------------------------------------------------------------------


def test_recovery_copy_is_saved_found_and_cleared(tmp_path: Path) -> None:
    recovery_dir = tmp_path / "recuperació"
    assert find_recovery(recovery_dir) is None
    photo_paths = make_files(tmp_path / "fotos", ["a.jpg"])
    project = simple_project(photo_paths)
    saved = save_recovery(project, recovery_dir)
    assert find_recovery(recovery_dir) == saved
    result = open_project(saved)
    assert result.missing_files == ()
    assert result.project.photos[0].path == photo_paths[0]
    clear_recovery(recovery_dir)
    clear_recovery(recovery_dir)  # nothing to clear
    assert find_recovery(recovery_dir) is None


# --- Speed ----------------------------------------------------------------------------------------


def test_a_project_of_1000_photos_saves_and_opens_in_less_than_a_second(tmp_path: Path) -> None:
    photo_paths = [tmp_path / "fotos" / f"IMG_{i:04d}.jpg" for i in range(1000)]
    project = simple_project(photo_paths, [tmp_path / "música.mp3"])
    path = tmp_path / "gran.passimaker"
    start = time.perf_counter()
    save_project(project, path)
    result = open_project(path)
    elapsed = time.perf_counter() - start
    assert [p.path for p in result.project.photos] == photo_paths
    assert len(result.missing_files) == 1001
    assert elapsed < 1.0, f"{elapsed:.2f} s"
