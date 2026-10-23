"""The whole path of §1.0 without a screen: photos, two songs, fit, save, close, open and export."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from passimaker.export import ExportResult, ExportStatus
from passimaker.ffmpeg import probe
from passimaker.ui.duration_status import Balance
from passimaker.ui.main_window import MainWindow
from tests.ui.conftest import build_window
from tests.ui.helpers import (
    FakeThumbnailService,
    RecordedQuestions,
    controller_with,
    write_photos,
    write_song,
)

pytestmark = [pytest.mark.ui, pytest.mark.lent]

TIMEOUT_MS = 30_000
EXPORT_TIMEOUT_MS = 180_000


def test_import_music_fit_save_reopen_and_export_ten_seconds(
    qtbot: QtBot, thumbnails: FakeThumbnailService, tmp_path: Path
) -> None:
    photos = write_photos(tmp_path / "fotos", [f"IMG_{i:02d}.jpg" for i in range(1, 7)], size=(640, 480))
    songs = [
        write_song(tmp_path / "musica" / "a.wav", 4.0),
        write_song(tmp_path / "musica" / "b.wav", 6.0, 660.0),
    ]
    questions = RecordedQuestions(folder=tmp_path / "fotos")
    questions.music = songs
    questions.save_path = tmp_path / "projecte" / "Passi de prova"

    first: MainWindow = build_window(qtbot, controller_with(0), thumbnails, questions)
    with qtbot.waitSignal(first.importer.finished, timeout=TIMEOUT_MS):
        first.add_folder_action.trigger()
    assert len(first.controller.project.photos) == len(photos)
    with qtbot.waitSignal(first.songs.finished, timeout=TIMEOUT_MS):
        first.add_music_action.trigger()
    assert first.duration_status.balance is Balance.MUSIC_SHORTER  # 10 s of music for 6 x 2 s of photos
    first.fit_to_music_action.trigger()
    assert first.duration_status.balance is Balance.EQUAL
    first.save_action.trigger()
    saved = tmp_path / "projecte" / "Passi de prova.pmk"
    assert saved.is_file()
    assert not first.isWindowModified()
    assert first.close()
    assert questions.asked_save == []  # nothing left to save

    second = build_window(qtbot, controller_with(0), thumbnails, questions)
    second.files.startup(saved)
    project = second.controller.project
    assert [p.path for p in project.photos] == photos
    assert [s.path for s in project.music.songs] == songs
    questions.export_path = tmp_path / "video" / "passi"
    (tmp_path / "video").mkdir()
    with qtbot.waitSignal(second.video_export.finished, timeout=EXPORT_TIMEOUT_MS) as blocker:
        second.export_action.trigger()
    assert blocker.args is not None
    result = blocker.args[0]
    assert isinstance(result, ExportResult)
    assert result.status is ExportStatus.DONE, result.reason_key
    video = tmp_path / "video" / "passi.mp4"
    info = probe(video)
    assert info.has_video and info.has_audio
    assert (info.width, info.height) == (1920, 1080)
    assert info.duration_s == pytest.approx(10.0, abs=0.1)
    dialog = second.video_export.dialog
    assert dialog is not None
    assert dialog.title_label.text().startswith("Vídeo desat (0:10, ")
    dialog.close_button.click()
    assert second.close()
