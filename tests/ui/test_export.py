"""[Exportar vídeo] from the window (§1.9): destination, progress dialog, cancel, errors, the end."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QUrl
from pytestqt.qtbot import QtBot

from passimaker.common import CancelToken
from passimaker.export import ExportResult, ExportStatus
from passimaker.model import Photo, Project, ProjectController
from passimaker.model.commands import AddPhotos
from passimaker.ui.export_dialog import ExportDialog
from passimaker.ui.main_window import MainWindow
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, write_photos

pytestmark = pytest.mark.ui

EXPORT_TIMEOUT_MS = 120_000


def real_window(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, folder: Path, count: int
) -> MainWindow:
    paths = write_photos(folder, [f"foto_{i:02d}.jpg" for i in range(1, count + 1)])
    photos = tuple(
        Photo(id=f"p{i:04d}", path=path, relative_path=None, width=320, height=240)
        for i, path in enumerate(paths, start=1)
    )
    controller = ProjectController(Project(name="Excursió", seed=3))
    controller.execute(AddPhotos(photos))
    return build_window(qtbot, controller, thumbnails, questions)


def export_and_wait(qtbot: QtBot, window: MainWindow) -> ExportDialog:
    with qtbot.waitSignal(window.video_export.finished, timeout=EXPORT_TIMEOUT_MS):
        window.export_action.trigger()
    dialog = window.video_export.dialog
    assert dialog is not None
    return dialog


def fake_exporter(result: ExportResult) -> Callable[..., ExportResult]:
    def run(
        project: Project, dest: Path, *, progress: Callable[[float, float | None], None], cancel: CancelToken
    ) -> ExportResult:
        progress(0.25, 30.0)
        return result

    return run


def test_the_save_dialog_proposes_the_project_name_in_the_videos_folder(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = real_window(qtbot, thumbnails, questions, tmp_path / "fotos", 2)
    questions.export_path = None  # the user cancels the save dialog
    window.export_action.trigger()
    assert [path.name for path in questions.suggested_exports] == ["Excursió.mp4"]
    assert window.video_export.dialog is None
    window.close()


def test_cancel_from_the_dialog_leaves_no_file(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = real_window(qtbot, thumbnails, questions, tmp_path / "fotos", 15)  # 30 s of video
    questions.export_path = tmp_path / "sortida" / "cancel·lat"
    (tmp_path / "sortida").mkdir()
    window.export_action.trigger()
    dialog = window.video_export.dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.windowModality() is Qt.WindowModality.WindowModal
    assert not window.export_action.isEnabled()  # §1.9: no second export, no editing meanwhile
    qtbot.waitUntil(lambda: dialog.progress_bar.value() > 0, timeout=EXPORT_TIMEOUT_MS)
    with qtbot.waitSignal(window.video_export.finished, timeout=10_000) as blocker:
        dialog.cancel_button.click()
    assert blocker.args is not None
    result = blocker.args[0]
    assert isinstance(result, ExportResult)
    assert result.status is ExportStatus.CANCELLED
    assert list((tmp_path / "sortida").iterdir()) == []  # neither the video nor the .part
    assert dialog.title_label.text() == "S'ha cancel·lat l'exportació. No s'ha desat cap fitxer."
    assert dialog.close_button.isVisible()
    assert not dialog.open_video_button.isVisible()
    assert window.export_action.isEnabled()
    dialog.close_button.click()
    window.close()


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("export.disk_full", "No hi ha prou espai al disc."),
        ("ffmpeg.disk_full", "El disc és ple. Allibera espai i torna-ho a provar."),
    ],
)
def test_a_full_disk_is_explained_in_catalan(
    qtbot: QtBot,
    thumbnails: FakeThumbnailService,
    questions: RecordedQuestions,
    tmp_path: Path,
    key: str,
    text: str,
) -> None:
    window = real_window(qtbot, thumbnails, questions, tmp_path / "fotos", 2)
    window.video_export.exporter = fake_exporter(ExportResult(ExportStatus.ERROR, key, 0.0, 0))
    questions.export_path = tmp_path / "ple.mp4"
    dialog = export_and_wait(qtbot, window)
    assert dialog.title_label.text() == "No s'ha pogut exportar el vídeo."
    assert dialog.message_label.text() == text
    assert dialog.message_label.isVisible()
    assert not dialog.open_video_button.isVisible()
    dialog.close_button.click()
    window.close()


def test_progress_shows_percentage_and_remaining_time(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = real_window(qtbot, thumbnails, questions, tmp_path / "fotos", 2)
    window.video_export.exporter = fake_exporter(ExportResult(ExportStatus.DONE, None, 270.0, 245_000_000))
    questions.export_path = tmp_path / "fet"
    dialog = export_and_wait(qtbot, window)
    assert dialog.job.dest == tmp_path / "fet.mp4"
    assert dialog.title_label.text() == "Vídeo desat (4:30, 245 MB)"
    assert dialog.percent_label.text() == "100 %"
    opened: list[QUrl] = []
    dialog.opener = lambda url: opened.append(url) or True
    dialog.open_video_button.click()
    dialog.show_folder_button.click()
    assert [url.toLocalFile() for url in opened] == [str(tmp_path / "fet.mp4"), str(tmp_path)]
    dialog.close_button.click()
    window.close()


def test_the_remaining_time_is_shown_while_exporting(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = real_window(qtbot, thumbnails, questions, tmp_path / "fotos", 2)
    window.video_export.exporter = fake_exporter(ExportResult(ExportStatus.DONE, None, 4.0, 1_000))
    questions.export_path = tmp_path / "x.mp4"
    dialog = export_and_wait(qtbot, window)
    dialog._on_progress(0.5, 75.0)  # what a second progress report would show before the end
    assert dialog.remaining_label.text() == "Queden 1:15"
    dialog.close_button.click()
    window.close()


def test_missing_files_are_listed_and_nothing_is_exported(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = real_window(qtbot, thumbnails, questions, tmp_path / "fotos", 3)
    lost = window.controller.project.photos[1].path
    lost.unlink()
    window.export_action.trigger()
    assert questions.missing_reports == [[lost]]
    assert questions.suggested_exports == []
    assert window.video_export.dialog is None
    window.close()
