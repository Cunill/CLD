"""B12: `PassiMaker.exe --autoprova` (passimaker.cli.main_selftest) and the launcher of the package."""

from __future__ import annotations

import importlib.util
import sys
import wave
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from passimaker import cli
from passimaker.ffmpeg import ENV_VAR, probe

LAUNCHER = Path(__file__).resolve().parents[3] / "packaging" / "launcher.py"


def _launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("passimaker_launcher", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selftest_files(tmp_path: Path) -> None:
    photos, song = cli.write_selftest_files(tmp_path)
    sizes = sorted(Image.open(p).size for p in photos.iterdir())
    assert sizes == sorted(cli.SELF_TEST_PHOTOS)
    with wave.open(str(song)) as tone:
        assert tone.getnchannels() == 2
        assert tone.getnframes() / tone.getframerate() == pytest.approx(cli.SELF_TEST_DURATION_S)


@pytest.mark.lent
def test_selftest_exports_five_seconds(tmp_path: Path) -> None:
    kept = tmp_path / "prova àè"
    report = tmp_path / "informe" / "autoprova.txt"
    assert cli.main_selftest(["--conservar", str(kept), "--informe", str(report)]) == cli.EXIT_OK
    info = probe(kept / "autoprova.mp4")
    assert (info.width, info.height) == (1920, 1080)
    assert info.has_audio
    assert info.duration_s == pytest.approx(cli.SELF_TEST_DURATION_S, abs=cli.SELF_TEST_TOLERANCE_S)
    assert (kept / "autoprova.pmk").is_file()
    text = report.read_text(encoding="utf-8")
    assert "Autoprova correcta" in text
    assert "Vídeo desat" in text


def test_selftest_fails_without_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "no hi és"))
    monkeypatch.setattr(cli.tempfile, "tempdir", str(tmp_path))
    report = tmp_path / "autoprova.txt"
    assert cli.main_selftest(["--informe", str(report)]) == cli.EXIT_ERROR
    assert "No s'ha trobat FFmpeg" in report.read_text(encoding="utf-8")
    assert "No s'ha trobat FFmpeg" in capsys.readouterr().err  # the report is also written to stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ["autoprova.txt"]  # the temporary folder is deleted


def test_selftest_detects_a_wrong_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def short_render(project_path: Path, output: Path, **_: object) -> int:
        output.write_bytes(b"")
        return cli.EXIT_OK

    monkeypatch.setattr(cli, "render", short_render)
    report = tmp_path / "autoprova.txt"
    args = ["--conservar", str(tmp_path / "prova"), "--informe", str(report)]
    assert cli.main_selftest(args) == cli.EXIT_ERROR
    assert "Autoprova correcta" not in report.read_text(encoding="utf-8")


def test_launcher_runs_the_selftest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "main_selftest", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(sys, "argv", ["PassiMaker.exe", "--autoprova", "--informe", "x.txt"])
    assert _launcher().main() == 0
    assert calls == [["--informe", "x.txt"]]


def test_launcher_opens_the_window_with_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    import passimaker.ui.app

    calls: list[list[str]] = []
    monkeypatch.setattr(passimaker.ui.app, "main", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(sys, "argv", ["PassiMaker.exe", "C:/fotos/viatge.pmk"])
    assert _launcher().main() == 0
    assert calls == [["C:/fotos/viatge.pmk"]]


def test_launcher_without_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """A windowed PassiMaker.exe starts with sys.stdout and sys.stderr set to None."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _launcher()._ensure_streams()
    print("es descarta", file=sys.stderr)
    assert sys.stdout is not None and sys.stderr is not None
