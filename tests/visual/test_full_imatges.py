"""B6 · The review tool (full d'imatges) runs on the test photos and writes the sheet and a video."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from passimaker.ffmpeg import probe

TOOL = Path(__file__).resolve().parents[2] / "tools" / "full_imatges.py"
PHOTOS = (
    "ratio_4x3.jpg",
    "ratio_9x16.jpg",
    "pano_3x1.jpg",
    "tiny_320x240.jpg",
    "orient_6.jpg",
    "corrupt.jpg",
)


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("full_imatges", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def photo_folder(fixture_files: dict[str, Path], tmp_path: Path) -> Path:
    folder = tmp_path / "fotos"
    folder.mkdir()
    for name in PHOTOS:
        shutil.copy(fixture_files[name], folder / name)
    return folder


def test_sheet_and_video(photo_folder: Path, tmp_path: Path) -> None:
    tool = load_tool()
    sheet, video = tmp_path / "full.png", tmp_path / "mostra.mp4"
    args = [str(photo_folder), "-o", str(sheet), "--amplada", "160", "--video", str(video)]
    assert tool.main([*args, "--mida-video", "320x180"]) == 0
    with Image.open(sheet) as image:
        rows = len(PHOTOS)
        assert image.width == tool.GAP + 4 * (160 + tool.GAP)
        assert image.height == 40 + tool.LABEL_HEIGHT + rows * (tool.LABEL_HEIGHT + 90 + tool.GAP)
    info = probe(video)
    assert (info.width, info.height) == (320, 180)
    assert info.duration_s == pytest.approx(2.0 * len(PHOTOS), abs=0.1)


def test_vertical_sheet_in_sentinel_mode(photo_folder: Path, tmp_path: Path) -> None:
    tool = load_tool()
    sheet = tmp_path / "full_vertical.png"
    assert (
        tool.main([str(photo_folder), "-o", str(sheet), "--vertical", "--amplada", "90", "--sentinella"]) == 0
    )
    with Image.open(sheet) as image:
        assert image.height == 40 + tool.LABEL_HEIGHT + len(PHOTOS) * (tool.LABEL_HEIGHT + 160 + tool.GAP)


def test_empty_folder(tmp_path: Path) -> None:
    assert load_tool().main([str(tmp_path), "-o", str(tmp_path / "x.png")]) == 1
