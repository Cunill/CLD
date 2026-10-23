"""Screenshots of block B11 (music strip, warnings and dialogs), written to tests/_artefactes/ui/b11.

Like those of B10, they are not compared with anything: they let a person see the dialogs that
nobody can open on a screen in the cloud sessions or in the CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox, QWidget
from pytestqt.qtbot import QtBot

from passimaker.export import ExportResult, ExportStatus
from passimaker.model import Song
from passimaker.model.commands import AddSongs
from passimaker.ui.dialogs import DialogQuestions
from passimaker.ui.duration_status import FitCheck, FitProblem
from passimaker.ui.export_dialog import ExportDialog, ExportJob
from passimaker.ui.main_window import MainWindow
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with

pytestmark = pytest.mark.ui

ARTEFACTS = Path(__file__).resolve().parents[1] / "_artefactes" / "ui" / "b11"


def shoot(qtbot: QtBot, widget: QWidget, name: str) -> None:
    qtbot.wait(80)
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTEFACTS / f"{name}.png"
    assert widget.grab().save(str(path)), f"no s'ha pogut desar {path}"
    assert path.stat().st_size > 0


def shoot_box(qtbot: QtBot, box: QMessageBox, name: str) -> None:
    box.show()
    qtbot.waitExposed(box)
    shoot(qtbot, box, name)
    box.close()


def song(index: int, name: str, seconds: float) -> Song:
    return Song(
        id=f"s{index}", path=Path(f"/musica/{name}.mp3"), relative_path=None, original_duration_s=seconds
    )


def never_run(*_args: object, **_kwargs: object) -> ExportResult:
    raise AssertionError("the screenshots drive the dialog by hand")


def export_dialog(window: MainWindow) -> ExportDialog:
    job = ExportJob(window.controller.project, Path("/videos/Vacances.mp4"), never_run, window)
    dialog = ExportDialog(job, window)
    dialog.show()
    return dialog


def test_screenshots_of_block_b11(qtbot: QtBot, questions: RecordedQuestions) -> None:
    service = FakeThumbnailService()
    window = build_window(qtbot, controller_with(24), service, questions, size=(1100, 720))
    window.controller.execute(AddSongs((song(1, "Cançó A", 192), song(2, "Cançó B", 160))))
    window.view.request_visible_thumbnails()
    service.wait()
    shoot(qtbot, window, "01_musica_mes_llarga")

    window.fit_to_music()
    shoot(qtbot, window, "02_ajustat_a_la_musica")

    dialog = export_dialog(window)
    dialog._on_progress(0.42, 83.0)
    shoot(qtbot, dialog, "03_exportant")
    dialog._on_finished(ExportResult(ExportStatus.DONE, None, 270.0, 245_000_000))
    shoot(qtbot, dialog, "04_video_desat")
    dialog.close()

    dialog = export_dialog(window)
    dialog._on_progress(0.6, 20.0)
    dialog._on_finished(ExportResult(ExportStatus.ERROR, "export.disk_full", 0.0, 0))
    shoot(qtbot, dialog, "05_disc_ple")
    dialog.close()

    real = DialogQuestions(window)
    shoot_box(qtbot, real.fit_box(FitCheck(FitProblem.TOO_MANY_PHOTOS, 0.6)), "06_massa_fotos")
    shoot_box(qtbot, real.save_changes_box("Vacances"), "07_desar_els_canvis")
    shoot_box(qtbot, real.recovery_box(), "08_recuperar")
    shoot_box(qtbot, real.relink_box(12), "09_fitxers_que_no_es_troben")

    window.files.missing = (Path("/fotos/IMG_0001.jpg"),)
    window.files.missing_changed.emit()
    window.controller.execute(AddSongs((song(3, "Cançó C", 30),)))
    shoot(qtbot, window, "10_falten_fitxers")

    window.close()
    service.close()
    assert len(list(ARTEFACTS.glob("*.png"))) >= 10
