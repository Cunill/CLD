"""Screenshots of block B14 (photo, song and project panels), written to tests/_artefactes/ui/b14.

Like those of B10 and B11, they are not compared with anything: they let a person see the panels
that nobody can open on a screen in the cloud sessions or in the CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel
from pytestqt.qtbot import QtBot

from passimaker.model import Song
from passimaker.model.commands import AddSongs, SetPhotoDuration, SetPhotoMotion
from passimaker.model.types import MotionType
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with, write_song
from tests.ui.test_player_panel import wait_frame
from tests.ui.test_screenshots_b11 import shoot

pytestmark = pytest.mark.ui

ARTEFACTS = Path(__file__).resolve().parents[1] / "_artefactes" / "ui" / "b14"


def test_screenshots_of_the_b14_panels(
    qtbot: QtBot,
    thumbnails: FakeThumbnailService,
    questions: RecordedQuestions,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tests.ui.test_screenshots_b11.ARTEFACTS", ARTEFACTS)
    first = write_song(tmp_path / "Cançó A.wav", 12.0, 440.0)
    controller = controller_with(12)
    controller.execute(
        AddSongs(
            (
                Song(id="s1", path=first, relative_path=None, original_duration_s=12.0, trim_start_s=2.0),
                Song(id="s2", path=first, relative_path=None, original_duration_s=12.0, trim_end_s=9.0),
            )
        )
    )
    controller.execute(SetPhotoDuration(frozenset({"p0003"}), 2.6))
    controller.execute(SetPhotoMotion(frozenset({"p0005"}), MotionType.PAN_LEFT))
    window = build_window(qtbot, controller, thumbnails, questions, size=(1280, 860))
    thumbnails.wait()

    window.view.select_ids(["p0003"])
    wait_frame(qtbot, window.player_panel)
    shoot(qtbot, window, "01_finestra_amb_el_panell_de_foto")
    shoot(qtbot, window.properties, "02_panell_de_foto")

    window.view.select_ids(["p0003", "p0004", "p0005"])
    shoot(qtbot, window.properties, "03_panell_de_diverses_fotos")

    window.music_strip.view.selectionModel().select(
        window.music_strip.model.index(0, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect
    )
    bar = window.song_panel.trim_bar
    qtbot.waitUntil(lambda: bar.peaks is not None, timeout=10_000)
    shoot(qtbot, window, "04_finestra_amb_el_panell_de_canco")
    shoot(qtbot, window.properties, "05_panell_de_canco")

    window.properties.setCurrentIndex(window.properties.PROJECT)
    window.panel.advanced.setChecked(True)
    shoot(qtbot, window.properties, "06_panell_de_projecte_avancat")

    for name in (
        "01_finestra_amb_el_panell_de_foto",
        "02_panell_de_foto",
        "03_panell_de_diverses_fotos",
        "04_finestra_amb_el_panell_de_canco",
        "05_panell_de_canco",
        "06_panell_de_projecte_avancat",
    ):
        assert (ARTEFACTS / f"{name}.png").stat().st_size > 0
    window.close()
