"""B7: locate() search order and its error (with fake executables)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from passimaker import ffmpeg
from passimaker.ffmpeg import _locate


def _fake_bin(directory: Path, *names: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in names:
        exe = directory / f"{name}{suffix}"
        exe.write_bytes(b"")
        exe.chmod(0o755)
    return directory


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No env var, an empty vendor folder, an empty PATH and not frozen."""
    monkeypatch.delenv(ffmpeg.ENV_VAR, raising=False)
    monkeypatch.setattr(_locate, "VENDOR_DIR", tmp_path / "vendor")
    monkeypatch.setenv("PATH", str(tmp_path / "buit"))
    monkeypatch.delattr(sys, "frozen", raising=False)
    return tmp_path


def test_nothing_found_is_a_clear_error(isolated: Path) -> None:
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.locate()
    assert caught.value.message_key == ffmpeg.ERROR_NOT_FOUND
    assert "vendor" in caught.value.detail
    assert "PATH" in caught.value.detail


def test_environment_variable_comes_first(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_bin(isolated / "vendor", "ffmpeg", "ffprobe")
    chosen = _fake_bin(isolated / "triat per l'usuari", "ffmpeg", "ffprobe")
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(chosen))
    paths = ffmpeg.locate()
    assert paths.ffmpeg.parent == chosen
    assert paths.ffprobe.parent == chosen


def test_a_wrong_environment_variable_is_an_error(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_bin(isolated / "vendor", "ffmpeg", "ffprobe")
    only_ffmpeg = _fake_bin(isolated / "incomplet", "ffmpeg")
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(only_ffmpeg))
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.locate()
    assert caught.value.message_key == ffmpeg.ERROR_NOT_FOUND
    assert ffmpeg.ENV_VAR in caught.value.detail


def test_program_folder_comes_before_vendor(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_bin(isolated / "vendor", "ffmpeg", "ffprobe")
    program = _fake_bin(isolated / "PassiMaker", "ffmpeg", "ffprobe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(program / "PassiMaker.exe"))
    assert ffmpeg.locate().ffmpeg.parent == program.resolve()


def test_vendor_comes_before_path(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vendor = _fake_bin(isolated / "vendor", "ffmpeg", "ffprobe")
    on_path = _fake_bin(isolated / "sistema", "ffmpeg", "ffprobe")
    monkeypatch.setenv("PATH", str(on_path))
    assert ffmpeg.locate().ffmpeg.parent == vendor


def test_path_is_the_last_resort(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    on_path = _fake_bin(isolated / "sistema", "ffmpeg", "ffprobe")
    monkeypatch.setenv("PATH", str(on_path))
    paths = ffmpeg.locate()
    assert paths.ffmpeg.parent == on_path
    assert paths.ffprobe.parent == on_path


def test_both_programs_are_needed(isolated: Path) -> None:
    _fake_bin(isolated / "vendor", "ffmpeg")
    with pytest.raises(ffmpeg.FfmpegError):
        ffmpeg.locate()


def test_vendor_folder_is_the_one_in_the_repository() -> None:
    assert Path(__file__).resolve().parents[3] / "vendor" / "ffmpeg" / "bin" == _locate.VENDOR_DIR
