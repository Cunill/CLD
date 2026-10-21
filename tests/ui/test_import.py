"""Importing from the window: order, progress, cancellation and the questions of §1.1."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDropEvent
from pytestqt.qtbot import QtBot

from passimaker.importer import ImportFailure
from passimaker.model import defaults
from passimaker.ui.main_window import MainWindow
from tests.ui.helpers import RecordedQuestions, write_photos

pytestmark = pytest.mark.ui

TIMEOUT_MS = 30_000


def wait_import(qtbot: QtBot, window: MainWindow) -> int:
    with qtbot.waitSignal(window.importer.finished, timeout=TIMEOUT_MS) as blocker:
        pass
    return int(blocker.args[0]) if blocker.args else 0


def import_and_wait(qtbot: QtBot, window: MainWindow, paths: list[Path], index: int | None = None) -> int:
    with qtbot.waitSignal(window.importer.finished, timeout=TIMEOUT_MS) as blocker:
        window.import_paths(paths, index)
    return int(blocker.args[0]) if blocker.args else 0


def names(window: MainWindow) -> list[str]:
    return [photo.path.name for photo in window.controller.project.photos]


def test_dropping_twenty_files_and_a_folder_keeps_the_order_of_the_specification(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    files = write_photos(tmp_path / "soltes", [f"foto_{i:02d}.jpg" for i in range(1, 21)])
    folder = tmp_path / "carpeta"
    write_photos(folder, ["z_02.jpg", "z_10.jpg", "z_1.jpg"])
    added = import_and_wait(qtbot, window, [*files, folder])
    assert added == 23
    # §1.1: no EXIF date, so natural order by name ("z_1" before "z_2" and "z_10" last).
    assert names(window) == [f"foto_{i:02d}.jpg" for i in range(1, 21)] + ["z_1.jpg", "z_02.jpg", "z_10.jpg"]
    assert window.storyboard.currentWidget() is window.view
    assert window.status_label.text().startswith("23 fotos")


def test_dropping_on_the_window_imports(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    files = write_photos(tmp_path / "soltes", ["a.jpg", "b.jpg"])
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path)) for path in files])
    event = QDropEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    with qtbot.waitSignal(window.importer.finished, timeout=TIMEOUT_MS):
        window.dropEvent(event)
    assert names(window) == ["a.jpg", "b.jpg"]


def test_photos_dropped_on_the_storyboard_go_in_at_that_point(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    first = write_photos(tmp_path / "un", ["a.jpg", "b.jpg", "c.jpg"])
    import_and_wait(qtbot, window, first)
    extra = write_photos(tmp_path / "dos", ["nova.jpg"])
    with qtbot.waitSignal(window.importer.finished, timeout=TIMEOUT_MS):
        window.view.files_dropped.emit(extra, 1)
    assert names(window) == ["a.jpg", "nova.jpg", "b.jpg", "c.jpg"]


def test_the_progress_is_shown_and_counts_up(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    files = write_photos(tmp_path / "moltes", [f"f_{i:03d}.jpg" for i in range(40)])
    seen: list[tuple[int, int]] = []
    window.importer.progress.connect(lambda done, total: seen.append((done, total)))
    visible: list[bool] = []
    window.importer.started.connect(lambda: visible.append(window.progress_widget.isVisible()))
    import_and_wait(qtbot, window, files)
    assert visible == [True]
    assert seen, "no s'ha informat del progrés"
    assert [done for done, _ in seen] == sorted(done for done, _ in seen)
    assert seen[-1][1] == 40
    assert not window.progress_widget.isVisible()


def test_cancelling_an_import_adds_nothing(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    files = write_photos(tmp_path / "moltes", [f"f_{i:03d}.jpg" for i in range(150)])
    # Cancelling on the first progress report stops the scan halfway, as the button does.
    window.importer.progress.connect(lambda *_: window.importer.cancel())
    added = import_and_wait(qtbot, window, files)
    assert added == 0
    assert window.controller.project.photos == ()
    assert not window.progress_widget.isVisible()


def test_the_subfolders_are_asked_once(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    root = tmp_path / "arrel"
    write_photos(root, ["a.jpg", "b.jpg"])
    write_photos(root / "dins", ["c.jpg", "d.jpg", "e.jpg"])
    added = import_and_wait(qtbot, window, [root])
    assert questions.asked_subfolders == [3]
    assert added == 2


def test_accepting_the_subfolders_imports_them(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    questions.subfolders = True
    root = tmp_path / "arrel"
    write_photos(root, ["a.jpg"])
    write_photos(root / "dins", ["c.jpg", "d.jpg"])
    added = import_and_wait(qtbot, window, [root])
    assert questions.asked_subfolders == [2]
    assert added == 3


def test_repeated_photos_are_asked_once_and_refused_by_default(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    files = write_photos(tmp_path / "soltes", ["a.jpg", "b.jpg", "c.jpg"])
    import_and_wait(qtbot, window, files)
    added = import_and_wait(qtbot, window, files)
    assert questions.asked_duplicates == [3]
    assert added == 0
    assert len(window.controller.project.photos) == 3


def test_accepting_the_repeated_photos_adds_them_again(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    questions.duplicates = True
    files = write_photos(tmp_path / "soltes", ["a.jpg", "b.jpg"])
    import_and_wait(qtbot, window, files)
    added = import_and_wait(qtbot, window, files)
    assert added == 2
    assert len(window.controller.project.photos) == 4
    identifiers = {photo.id for photo in window.controller.project.photos}
    assert len(identifiers) == 4, "els identificadors han de ser únics"


def test_the_files_that_fail_are_reported(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    folder = tmp_path / "barreja"
    write_photos(folder, ["bona.jpg"])
    notes = folder / "notes.txt"
    notes.write_text("no és una foto", encoding="utf-8")
    (folder / "camera.cr2").write_bytes(b"raw")
    # A folder quietly ignores what is not a photo; a file given by hand is reported (§1.1).
    added = import_and_wait(qtbot, window, [folder, notes])
    assert added == 1
    reasons = {failure.reason for failure in questions.failures}
    assert reasons == {ImportFailure.UNSUPPORTED, ImportFailure.RAW}


def test_too_many_photos_warns(
    qtbot: QtBot,
    window: MainWindow,
    questions: RecordedQuestions,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(defaults, "MAX_PHOTOS_WITHOUT_WARNING", 2)
    files = write_photos(tmp_path / "soltes", ["a.jpg", "b.jpg", "c.jpg"])
    import_and_wait(qtbot, window, files)
    assert questions.many_photos == [3]


def test_choosing_photos_from_the_toolbar_imports_them(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    questions.photos = write_photos(tmp_path / "soltes", ["a.jpg", "b.jpg"])
    with qtbot.waitSignal(window.importer.finished, timeout=TIMEOUT_MS):
        window.add_photos_action.trigger()
    assert questions.chosen_photos == 1
    assert len(window.controller.project.photos) == 2


def test_choosing_a_folder_from_the_menu_imports_it(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    folder = tmp_path / "carpeta"
    write_photos(folder, ["a.jpg"])
    questions.folder = folder
    with qtbot.waitSignal(window.importer.finished, timeout=TIMEOUT_MS):
        window.add_folder_action.trigger()
    assert questions.chosen_folders == 1
    assert len(window.controller.project.photos) == 1
