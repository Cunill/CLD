"""Screenshots of the main states, written to tests/_artefactes/ui (a CI artefact).

They are not compared with anything: they are there so a person can look at the window of a
block that nobody can run on a screen (the sessions are on Linux and the CI has no display).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from passimaker.ui.delegate import ThumbnailSize
from passimaker.ui.main_window import MainWindow
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with

pytestmark = pytest.mark.ui

ARTEFACTS = Path(__file__).resolve().parents[1] / "_artefactes" / "ui"
TIMEOUT_MS = 20_000


def shoot(qtbot: QtBot, window: MainWindow, name: str) -> Path:
    qtbot.wait(120)
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTEFACTS / f"{name}.png"
    assert window.grab().save(str(path)), f"no s'ha pogut desar {path}"
    assert path.stat().st_size > 0
    return path


def settled(qtbot: QtBot, window: MainWindow, service: FakeThumbnailService) -> None:
    """Waits for every thumbnail asked for and for the fixed view."""
    window.view.request_visible_thumbnails()
    service.wait()
    qtbot.wait(150)
    window.still.wait(TIMEOUT_MS)
    qtbot.wait(100)


def test_screenshots_of_the_main_states(qtbot: QtBot, questions: RecordedQuestions) -> None:
    service = FakeThumbnailService()
    empty = build_window(qtbot, controller_with(0), service, questions)
    shoot(qtbot, empty, "01_estat_buit")
    empty.close()

    window = build_window(qtbot, controller_with(24), service, questions)
    settled(qtbot, window, service)
    shoot(qtbot, window, "02_storyboard")

    window.view.select_ids(["p0003", "p0004"])
    settled(qtbot, window, service)
    shoot(qtbot, window, "03_seleccio_i_vista_fixa")

    window.panel.advanced.setChecked(True)
    qtbot.wait(60)
    shoot(qtbot, window, "04_panell_avancat")

    window.format_action.setChecked(True)
    settled(qtbot, window, service)
    shoot(qtbot, window, "05_format_vertical")
    window.format_action.setChecked(False)

    window.set_thumbnail_size(ThumbnailSize.LARGE)
    settled(qtbot, window, service)
    shoot(qtbot, window, "06_miniatures_grans")

    window.set_thumbnail_size(ThumbnailSize.SMALL)
    settled(qtbot, window, service)
    shoot(qtbot, window, "07_miniatures_petites")

    window._on_import_started()
    window._on_import_progress(340, 1000)
    shoot(qtbot, window, "08_important")
    window._on_import_finished(0)

    window.close()
    service.close()
    assert sorted(path.name for path in ARTEFACTS.glob("*.png")) == [
        "01_estat_buit.png",
        "02_storyboard.png",
        "03_seleccio_i_vista_fixa.png",
        "04_panell_avancat.png",
        "05_format_vertical.png",
        "06_miniatures_grans.png",
        "07_miniatures_petites.png",
        "08_important.png",
    ]
