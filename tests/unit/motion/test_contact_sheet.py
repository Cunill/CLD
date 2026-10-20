"""B3 · The contact-sheet tool for milestone F1 runs on the test photos."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

TOOL = Path(__file__).resolve().parents[3] / "tools" / "full_contactes_moviments.py"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("full_contactes_moviments", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module to be registered
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def photo_folder(fixture_files: dict[str, Path], tmp_path: Path) -> Path:
    folder = tmp_path / "fotos"
    folder.mkdir()
    for name in (
        "ratio_4x3.jpg",
        "ratio_3x4.jpg",
        "pano_3x1.jpg",
        "photo.heic",
        "orient_6.jpg",
        "gray16.png",
        "corrupt.jpg",
    ):
        shutil.copy(fixture_files[name], folder / name)
    return folder


@pytest.mark.parametrize("vertical", [False, True])
def test_contact_sheet_is_written(photo_folder: Path, tmp_path: Path, vertical: bool) -> None:
    out = tmp_path / "full.png"
    args = [str(photo_folder), "-o", str(out), "--intensitat", "marcada"] + (
        ["--vertical"] if vertical else []
    )
    assert load_tool().main(args) == 0
    with Image.open(out) as sheet:
        assert sheet.width > 1000 and sheet.height > 400


def test_empty_folder_fails(tmp_path: Path) -> None:
    assert load_tool().main([str(tmp_path), "-o", str(tmp_path / "x.png")]) == 1


@pytest.mark.lent
def test_sample_video_is_written(photo_folder: Path, tmp_path: Path) -> None:
    video = tmp_path / "mostra.mp4"
    assert (
        load_tool().main(
            [str(photo_folder), "-o", str(tmp_path / "f.png"), "--video", str(video), "--durada", "2"]
        )
        == 0
    )
    assert video.stat().st_size > 10_000
