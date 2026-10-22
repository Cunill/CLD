"""Fixed view of the selected photo: it uses the real compositor, off the GUI thread."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from passimaker.model import OutputFormat
from passimaker.ui.main_window import MainWindow

pytestmark = pytest.mark.ui

TIMEOUT_MS = 20_000


def wait_frame(qtbot: QtBot, window: MainWindow) -> None:
    window.still.wait(TIMEOUT_MS)
    qtbot.waitUntil(lambda: window.still.pixmap is not None, timeout=TIMEOUT_MS)


def test_selecting_a_photo_draws_it(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.select_ids(["p0003"])
    wait_frame(qtbot, window)
    pixmap = window.still.pixmap
    assert pixmap is not None
    assert pixmap.width() > 0 and pixmap.height() > 0
    # The frame keeps the proportion of the chosen format (§1.11).
    width, height = OutputFormat.HORIZONTAL.size
    assert pixmap.width() / pixmap.height() == pytest.approx(width / height, rel=0.02)


def test_the_vertical_format_changes_the_shape(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.select_ids(["p0002"])
    wait_frame(qtbot, window)
    window.format_action.setChecked(True)
    window.still.wait(TIMEOUT_MS)
    qtbot.waitUntil(
        lambda: window.still.pixmap is not None
        and window.still.pixmap.height() > window.still.pixmap.width(),
        timeout=TIMEOUT_MS,
    )
    pixmap = window.still.pixmap
    assert pixmap is not None
    width, height = OutputFormat.VERTICAL.size
    assert pixmap.width() / pixmap.height() == pytest.approx(width / height, rel=0.02)


def test_without_a_selection_there_is_nothing_to_draw(qtbot: QtBot, window: MainWindow) -> None:
    window.still.show_photo(None)
    window.still.wait(TIMEOUT_MS)
    assert window.still.pixmap is None
