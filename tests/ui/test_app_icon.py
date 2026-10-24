"""The program icon: the window's (passimaker.ui.app) and the .exe's (packaging/PassiMaker.ico)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QSize
from pytestqt.qtbot import QtBot

from passimaker.ui.app import ICON_FILE, app_icon

pytestmark = pytest.mark.ui

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"


def test_the_window_icon_loads_at_every_size(qtbot: QtBot) -> None:
    icon = app_icon()
    assert not icon.isNull()
    for size in (16, 32, 256):
        assert not icon.pixmap(QSize(size, size)).isNull()


def test_the_window_icon_has_transparent_corners() -> None:
    image = Image.open(ICON_FILE)
    assert image.mode == "RGBA" and image.size == (256, 256)
    assert image.getpixel((0, 0))[3] < 8  # type: ignore[index]  # resampling leaves an invisible trace
    assert image.getpixel((128, 128))[3] == 255  # type: ignore[index]


def test_the_exe_icon_has_the_windows_sizes() -> None:
    with Image.open(PACKAGING / "PassiMaker.ico") as ico:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])
