"""B9: passimaker-nou and passimaker-render."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from passimaker import cli
from passimaker.model import FitMode, MotionMode, OutputFormat
from passimaker.model import defaults as model_defaults
from passimaker.projectio import open_project
from passimaker.timeline import compute_timeline
from tests.integration.export.conftest import ffprobe, photo_folder

PHOTOS = ("ratio_4x3.jpg", "ratio_9x16.jpg", "tiny_320x240.jpg", "orient_6.jpg")


@pytest.fixture
def folder(fixture_files: dict[str, Path], tmp_path: Path) -> Path:
    photos = photo_folder(fixture_files, tmp_path / "fotos de l'estiu", PHOTOS)
    for name in ("corrupt.jpg", "not_an_image.jpg"):
        (photos / name).write_bytes(fixture_files[name].read_bytes())
    photo_folder(fixture_files, photos / "subcarpeta", ("ratio_1x1.jpg",))
    return photos


def test_new_project_has_the_default_values(
    folder: Path, fixture_files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "projecte"
    music = [str(fixture_files["tone_440.mp3"]), str(fixture_files["tone_880.ogg"])]
    assert cli.main_new([str(folder), *music, "-o", str(output)]) == cli.EXIT_OK
    saved = output.with_suffix(".pmk")
    project = open_project(saved).project
    assert project.name == "projecte"
    assert project.output_format is OutputFormat.HORIZONTAL
    assert 0 <= project.seed < cli.NEW_SEED_LIMIT  # drawn at random (decision of the user)
    # corrupt.jpg has a valid header: B4 imports it (the compositor draws it grey, with a warning).
    assert sorted(p.path.name for p in project.photos) == sorted((*PHOTOS, "corrupt.jpg"))
    assert [s.path.name for s in project.music.songs] == ["tone_440.mp3", "tone_880.ogg"]
    assert [s.original_duration_s for s in project.music.songs] == pytest.approx([8.0, 10.0], abs=0.1)
    assert all(p.duration_s is None and p.fit is FitMode.AUTO for p in project.photos)
    assert all(p.motion.mode is MotionMode.AUTO for p in project.photos)
    assert project.default_duration_s == model_defaults.PHOTO_DURATION_S
    assert [p.low_resolution for p in project.photos if p.path.name == "tiny_320x240.jpg"] == [True]
    err = capsys.readouterr().err
    assert "not_an_image.jpg" in err  # skipped files are listed
    assert "subcarpetes" in err
    assert "Projecte desat" in err and f"llavor {project.seed})" in err


def test_new_project_options(folder: Path, fixture_files: dict[str, Path], tmp_path: Path) -> None:
    output = tmp_path / "vertical.pmk"
    song = str(fixture_files["tone_880.wav"])
    args = [str(folder), song, "-o", str(output), "--vertical", "--ajustar", "--llavor", "42"]
    assert cli.main_new(args) == cli.EXIT_OK
    project = open_project(output).project
    assert project.output_format is OutputFormat.VERTICAL
    assert project.seed == 42
    # Fitted to the 10 s song: the show lasts as long as the music (within the 1-3 s limits).
    assert compute_timeline(project).total_duration_s == pytest.approx(10.0, abs=0.05)


@pytest.mark.parametrize("output_format", list(OutputFormat))
def test_new_project_with_each_format(folder: Path, tmp_path: Path, output_format: OutputFormat) -> None:
    """M10: --format chooses any of the six proportions."""
    output = tmp_path / "format.pmk"
    args = [str(folder), "-o", str(output), "--format", output_format.label, "--llavor", "1"]
    assert cli.main_new(args) == cli.EXIT_OK
    assert open_project(output).project.output_format is output_format


def test_vertical_and_format_must_agree(
    folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "p.pmk"
    agreeing = [str(folder), "-o", str(output), "--vertical", "--format", "9:16"]
    assert cli.main_new(agreeing) == cli.EXIT_OK
    assert open_project(output).project.output_format is OutputFormat.VERTICAL
    output.unlink()
    assert cli.main_new([str(folder), "-o", str(output), "--vertical", "--format", "4:3"]) == cli.EXIT_ERROR
    assert "no coincideixen" in capsys.readouterr().err
    assert not output.exists()
    with pytest.raises(SystemExit):
        cli.main_new([str(folder), "-o", str(output), "--format", "1:1"])


def test_the_same_folder_and_seed_give_the_same_project(folder: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a.pmk", tmp_path / "b.pmk"
    assert cli.main_new([str(folder), "-o", str(first), "--llavor", "5"]) == cli.EXIT_OK
    assert cli.main_new([str(folder), "-o", str(second), "--llavor", "5"]) == cli.EXIT_OK
    a, b = open_project(first).project, open_project(second).project
    assert [p.motion for p in a.photos] == [p.motion for p in b.photos]


def test_new_project_errors(tmp_path: Path, folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / "buida"
    empty.mkdir()
    assert cli.main_new([str(empty), "-o", str(tmp_path / "x.pmk")]) == cli.EXIT_ERROR
    assert cli.main_new([str(tmp_path / "no hi és"), "-o", str(tmp_path / "x.pmk")]) == cli.EXIT_ERROR
    missing_song = str(tmp_path / "cançó.mp3")
    assert cli.main_new([str(folder), missing_song, "-o", str(tmp_path / "x.pmk")]) == cli.EXIT_ERROR
    assert "No es troba el fitxer" in capsys.readouterr().err
    assert not (tmp_path / "x.pmk").exists()


def test_render_refuses_a_project_with_missing_files(folder: Path, tmp_path: Path) -> None:
    project = tmp_path / "p.pmk"
    assert cli.main_new([str(folder), "-o", str(project)]) == cli.EXIT_OK
    (folder / "ratio_4x3.jpg").unlink()
    err = io.StringIO()
    assert cli.render(project, tmp_path / "v.mp4", err=err) == cli.EXIT_ERROR
    assert "no es troben 1 fitxers" in err.getvalue()
    assert "ratio_4x3.jpg" in err.getvalue()
    assert not (tmp_path / "v.mp4").exists()


def test_render_of_a_file_that_is_not_a_project(tmp_path: Path) -> None:
    bad = tmp_path / "malmès.pmk"
    bad.write_text("no és json", encoding="utf-8")
    err = io.StringIO()
    assert cli.render(bad, tmp_path / "v.mp4", err=err) == cli.EXIT_ERROR
    assert "malmès" in err.getvalue()


@pytest.mark.lent
def test_new_and_render_make_a_video(
    folder: Path, fixture_files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "passi.pmk"
    video = tmp_path / "vídeos" / "passi d'estiu.mp4"
    video.parent.mkdir()
    assert cli.main_new([str(folder), str(fixture_files["tone_660.flac"]), "-o", str(project)]) == cli.EXIT_OK
    assert cli.main_render([str(project), str(video)]) == cli.EXIT_OK
    timeline = compute_timeline(open_project(project).project)
    info = ffprobe(video)
    assert abs(int(str(info.video["nb_frames"])) - timeline.total_frames) <= 1
    assert info.audio is not None
    err = capsys.readouterr().err
    assert "Exportant… 100%" in err
    assert "Vídeo desat" in err and "imatges/s" in err


def test_progress_printer_without_terminal() -> None:
    out = io.StringIO()
    printer = cli._ProgressPrinter(out)  # pyright: ignore[reportPrivateUsage]
    for i in range(101):
        printer(i / 100, 50 - i / 2)
    printer.end()
    lines = out.getvalue().splitlines()
    assert len(lines) == 11
    assert lines[0] == "Exportant… 0% (queden 0:50)"
    assert lines[-1] == "Exportant… 100% (queden 0:00)"


def test_without_a_seed_each_new_project_gets_its_own(folder: Path, tmp_path: Path) -> None:
    """Each new project draws its own seed (so its own motions) and keeps it: reopening it gives the
    same project, and the printed seed rebuilds it."""
    seeds = set()
    for i in range(4):
        output = tmp_path / f"p{i}.pmk"
        assert cli.main_new([str(folder), "-o", str(output)]) == cli.EXIT_OK
        seeds.add(open_project(output).project.seed)
    assert len(seeds) > 1  # 4 draws among a million
    first = open_project(tmp_path / "p0.pmk").project
    again = tmp_path / "again.pmk"
    assert cli.main_new([str(folder), "-o", str(again), "--llavor", str(first.seed)]) == cli.EXIT_OK
    assert [p.motion for p in open_project(again).project.photos] == [p.motion for p in first.photos]
