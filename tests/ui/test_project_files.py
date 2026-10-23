"""Saving and opening projects from the window (§1.10): title, recents, recovery and relinking."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDropEvent
from pytestqt.qtbot import QtBot

from passimaker.model import Photo, ProjectController, Song
from passimaker.model.commands import AddPhotos, AddSongs, SetDefaultDuration
from passimaker.projectio import find_recovery, open_project, save_project, save_recovery
from passimaker.ui.main_window import MainWindow
from passimaker.ui.music_strip import read_song
from passimaker.ui.project_files import LOCK_FILE_NAME, SaveAnswer, default_recovery_dir
from tests.ui.conftest import build_window
from tests.ui.helpers import (
    FakeThumbnailService,
    RecordedQuestions,
    controller_with,
    write_photos,
    write_song,
)

pytestmark = pytest.mark.ui


def real_photos(folder: Path, count: int) -> tuple[Photo, ...]:
    paths = write_photos(folder, [f"foto_{i:02d}.jpg" for i in range(1, count + 1)])
    return tuple(
        Photo(id=f"p{i:04d}", path=path, relative_path=None, width=320, height=240)
        for i, path in enumerate(paths, start=1)
    )


def test_the_title_has_an_asterisk_until_the_project_is_saved(
    window_with_photos: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = window_with_photos
    assert window.isWindowModified()
    assert "Sense títol" in window.windowTitle()
    questions.save_path = tmp_path / "Vacances"
    window.save_action.trigger()
    saved = tmp_path / "Vacances.pmk"
    assert saved.is_file()
    assert window.files.path == saved
    assert not window.isWindowModified()
    assert window.windowTitle().startswith("Vacances")
    window.controller.execute(SetDefaultDuration(3.0))
    assert window.isWindowModified()
    window.save_action.trigger()  # Ctrl+S with a file already: no question
    assert not window.isWindowModified()
    assert open_project(saved).project.default_duration_s == 3.0


def test_save_as_writes_another_file_and_both_are_recent(
    window_with_photos: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = window_with_photos
    questions.save_path = tmp_path / "u.pmk"
    window.save_action.trigger()
    questions.save_path = tmp_path / "dos.pmk"
    window.save_as_action.trigger()
    assert window.files.path == tmp_path / "dos.pmk"
    assert window.files.recent()[:2] == [tmp_path / "dos.pmk", tmp_path / "u.pmk"]
    window._fill_recent_menu()
    assert [action.text() for action in window.recent_menu.actions()] == ["dos", "u"]


def test_closing_with_changes_asks_and_cancel_keeps_the_window(
    window_with_photos: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = window_with_photos
    questions.save_answer = SaveAnswer.CANCEL
    assert not window.close()
    assert questions.asked_save == ["Sense títol"]
    assert window.isVisible()
    questions.save_answer = SaveAnswer.SAVE
    questions.save_path = tmp_path / "en_tancar.pmk"
    assert window.close()
    assert (tmp_path / "en_tancar.pmk").is_file()


def test_open_asks_to_save_first_and_loads_the_project(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    other = controller_with(5).project
    save_project(other, tmp_path / "altre.pmk")
    window = build_window(qtbot, controller_with(3), thumbnails, questions)
    questions.open_path = tmp_path / "altre.pmk"
    window.open_action.trigger()
    assert questions.asked_save == ["Sense títol"]  # discarded
    assert len(window.controller.project.photos) == 5
    assert window.files.path == tmp_path / "altre.pmk"
    assert not window.isWindowModified()
    assert not window.controller.can_undo
    window.close()


def test_a_project_given_as_argument_or_dropped_is_opened(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    save_project(controller_with(4).project, tmp_path / "argument.pmk")
    save_project(controller_with(2).project, tmp_path / "deixat.pmk")
    window.files.startup(tmp_path / "argument.pmk")
    assert len(window.controller.project.photos) == 4
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(tmp_path / "deixat.pmk"))])
    event = QDropEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert len(window.controller.project.photos) == 2
    assert window.files.path == tmp_path / "deixat.pmk"
    assert questions.errors == []


def test_a_damaged_project_shows_a_catalan_message(
    window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    damaged = tmp_path / "malmes.pmk"
    damaged.write_text("{ això no és json", encoding="utf-8")
    assert not window.files.open_path(damaged)
    assert questions.errors == ["El fitxer del projecte està malmès i no es pot obrir."]
    assert window.files.path is None


def test_recent_projects_appear_on_the_empty_screen(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions, tmp_path: Path
) -> None:
    first = build_window(qtbot, controller_with(2), thumbnails, questions)
    questions.save_path = tmp_path / "recent.pmk"
    first.save_action.trigger()
    first.close()
    second = build_window(qtbot, controller_with(0), thumbnails, questions)
    recent = second.recent_projects
    assert recent.isVisible()
    assert [button.text() for button in recent.buttons] == ["recent"]
    recent.buttons[0].click()
    assert len(second.controller.project.photos) == 2
    second.close()


# --- Recovery after a crash (§1.10) ---------------------------------------------------------------


def simulate_crash(window: MainWindow) -> Path:
    """The window disappears without its closeEvent (no question, no clean-up). Its process is
    gone, so its lock file names a process that no longer runs: QLockFile treats it as stale."""
    folder = window.files.own_recovery_dir
    window.files.autosave_timer.stop()
    lock = window.files._own_lock  # pyright: ignore[reportPrivateUsage]
    assert lock is not None
    # Qt's own lock file (process id, program, host…) with the id of a process that does not run.
    lines = (folder / LOCK_FILE_NAME).read_bytes().split(b"\n")
    lock.unlock()
    (folder / LOCK_FILE_NAME).write_bytes(b"\n".join([str(DEAD_PID).encode(), *lines[1:]]))
    window.files._own_lock = None  # pyright: ignore[reportPrivateUsage]
    window.hide()
    window.deleteLater()
    return folder


DEAD_PID = 2_000_000_000
"""Larger than any process id Windows or Linux hands out."""


def test_recovery_after_a_simulated_crash(
    qtbot: QtBot, thumbnails: FakeThumbnailService, tmp_path: Path
) -> None:
    questions = RecordedQuestions()
    crashed = build_window(qtbot, controller_with(7), thumbnails, questions)
    crashed.controller.execute(SetDefaultDuration(2.5))
    assert crashed.files.autosave_timer.interval() == 120_000  # §1.10: every 2 minutes
    crashed.files.autosave()  # what the timer does
    assert find_recovery(crashed.files.own_recovery_dir) is not None
    old_folder = simulate_crash(crashed)

    questions = RecordedQuestions(photos=[])
    reopened = build_window(qtbot, controller_with(0), thumbnails, questions)
    reopened.files.startup(None)
    assert questions.offered_recovery == 1
    project = reopened.controller.project
    assert len(project.photos) == 7
    assert project.default_duration_s == 2.5
    assert reopened.isWindowModified()  # a recovered project is not saved anywhere yet
    # The copy moved to the new window's folder: a second crash would not lose it.
    assert not old_folder.exists()
    assert find_recovery(reopened.files.own_recovery_dir) is not None
    questions.save_path = tmp_path / "recuperat.pmk"
    reopened.save_action.trigger()
    assert find_recovery(reopened.files.own_recovery_dir) is None
    reopened.close()


def test_declining_the_recovery_deletes_it(qtbot: QtBot, thumbnails: FakeThumbnailService) -> None:
    crashed = build_window(qtbot, controller_with(3), thumbnails, RecordedQuestions())
    crashed.controller.execute(SetDefaultDuration(2.5))
    crashed.files.autosave()
    folder = simulate_crash(crashed)
    questions = RecordedQuestions()
    questions.recover = False
    window = build_window(qtbot, controller_with(0), thumbnails, questions)
    window.files.startup(None)
    assert questions.offered_recovery == 1
    assert window.controller.project.photos == ()
    assert not folder.exists()
    window.close()


def test_a_clean_exit_leaves_no_recovery(window_with_photos: MainWindow) -> None:
    window_with_photos.files.autosave()
    folder = window_with_photos.files.own_recovery_dir
    assert find_recovery(folder) is not None
    window_with_photos.close()  # the questions answer "No desar"
    assert not folder.exists()
    assert list(default_recovery_dir().iterdir()) == []


def test_nothing_is_copied_without_changes(window: MainWindow) -> None:
    window.files.autosave()
    assert find_recovery(window.files.own_recovery_dir) is None


def test_two_open_windows_keep_their_own_copy(
    qtbot: QtBot, thumbnails: FakeThumbnailService, window_with_photos: MainWindow
) -> None:
    """Decision 0010: a second window neither offers nor overwrites the copy of one still open."""
    window_with_photos.files.autosave()
    first_copy = find_recovery(window_with_photos.files.own_recovery_dir)
    assert first_copy is not None
    before = first_copy.read_bytes()
    questions = RecordedQuestions()
    second = build_window(qtbot, controller_with(2), thumbnails, questions)
    second.files.startup(None)
    assert questions.offered_recovery == 0
    second.controller.execute(SetDefaultDuration(7.0))
    second.files.autosave()
    assert second.files.own_recovery_dir != window_with_photos.files.own_recovery_dir
    assert first_copy.read_bytes() == before
    second.close()
    assert first_copy.exists()


def test_the_copies_of_two_crashed_windows_are_offered_newest_first(
    qtbot: QtBot, thumbnails: FakeThumbnailService
) -> None:
    folders: list[Path] = []
    for count in (2, 5):
        crashed = build_window(qtbot, controller_with(count), thumbnails, RecordedQuestions())
        crashed.controller.execute(SetDefaultDuration(3.0))
        crashed.files.autosave()
        folders.append(simulate_crash(crashed))
    older = find_recovery(folders[0])
    assert older is not None
    os.utime(older, (1_000_000_000, 1_000_000_000))

    questions = RecordedQuestions(photos=[])
    window = build_window(qtbot, controller_with(0), thumbnails, questions)
    window.files.startup(None)
    assert questions.offered_recovery == 1
    assert len(window.controller.project.photos) == 5  # the newest
    assert folders[0].exists()  # waits for the next start
    window.close()

    questions = RecordedQuestions(photos=[])
    window = build_window(qtbot, controller_with(0), thumbnails, questions)
    window.files.startup(None)
    assert len(window.controller.project.photos) == 2
    window.close()


def test_a_copy_from_the_single_copy_version_is_still_offered(
    qtbot: QtBot, thumbnails: FakeThumbnailService
) -> None:
    root = default_recovery_dir()
    save_recovery(controller_with(4).project, root)
    questions = RecordedQuestions(photos=[])
    window = build_window(qtbot, controller_with(0), thumbnails, questions)
    window.files.startup(None)
    assert len(window.controller.project.photos) == 4
    assert find_recovery(root) is None
    window.close()


# --- Relinking (§1.10) ----------------------------------------------------------------------------


def test_relink_from_a_folder(qtbot: QtBot, thumbnails: FakeThumbnailService, tmp_path: Path) -> None:
    photos = real_photos(tmp_path / "original" / "fotos", 4)
    song = read_song(write_song(tmp_path / "original" / "musica" / "tema.wav", 2.0))
    assert isinstance(song, Song)
    controller = ProjectController()
    controller.execute(AddPhotos(photos))
    controller.execute(AddSongs((song,)))
    save_project(controller.project, tmp_path / "projectes" / "passi.pmk")
    # The photos and the music move elsewhere: neither the absolute nor the relative path works.
    shutil.move(tmp_path / "original", tmp_path / "mogut")

    questions = RecordedQuestions()
    questions.relink_folder = tmp_path / "mogut"
    window = build_window(qtbot, controller_with(0), thumbnails, questions)
    with qtbot.waitSignal(window.files.relinked, timeout=30_000):
        window.files.open_path(tmp_path / "projectes" / "passi.pmk")
    assert questions.asked_relink == [5]
    assert questions.relinked == [(5, 0)]
    project = window.controller.project
    assert all(photo.path.is_file() for photo in project.photos)
    assert project.music.songs[0].path == tmp_path / "mogut" / "musica" / "tema.wav"
    assert window.files.missing == ()
    assert not window.missing_bar.isVisible()
    assert window.isWindowModified()  # relinked paths are saved with the next Desar
    window.close()


def test_missing_files_stay_marked_until_found(
    qtbot: QtBot, thumbnails: FakeThumbnailService, tmp_path: Path
) -> None:
    photos = real_photos(tmp_path / "fotos", 3)
    controller = ProjectController()
    controller.execute(AddPhotos(photos))
    save_project(controller.project, tmp_path / "passi.pmk")
    photos[1].path.unlink()

    questions = RecordedQuestions()  # "Ara no"
    window = build_window(qtbot, controller_with(0), thumbnails, questions)
    window.files.open_path(tmp_path / "passi.pmk")
    assert questions.asked_relink == [1]
    assert window.files.missing_ids() == {"p0002"}
    assert window.missing_bar.isVisible()
    assert window.missing_bar.label.text() == "No es troben 1 fitxers."
    assert window.find_missing_action.isEnabled()

    write_photos(tmp_path / "copia", ["foto_02.jpg"])
    questions.folder = tmp_path / "copia"
    with qtbot.waitSignal(window.files.relinked, timeout=30_000):
        window.missing_bar.button.click()
    assert questions.relinked == [(1, 0)]
    assert window.files.missing_ids() == frozenset()
    assert not window.missing_bar.isVisible()
    window.close()
