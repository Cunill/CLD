"""The main window: layout of §1.0, empty state, status bar and the actions of the toolbar."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QKeySequence

from passimaker.model import OutputFormat
from passimaker.ui.delegate import ThumbnailSize
from passimaker.ui.main_window import MainWindow
from tests.ui.helpers import RecordedQuestions

pytestmark = pytest.mark.ui


def test_empty_state_shows_the_instructions(window: MainWindow) -> None:
    assert window.storyboard.currentWidget() is window.storyboard.empty
    assert "Arrossega" in window.storyboard.empty.label.text()
    assert window.status_label.text() == "0 fotos · 0:00"


def test_the_storyboard_replaces_the_empty_state_when_photos_arrive(
    window_with_photos: MainWindow,
) -> None:
    assert window_with_photos.storyboard.currentWidget() is window_with_photos.view
    assert window_with_photos.view.model().rowCount() == 12


def test_the_status_bar_shows_the_photos_and_the_total(window_with_photos: MainWindow) -> None:
    # 12 photos of 2.0 s each (the default of §1.0) = 24 s.
    assert window_with_photos.status_label.text() == "12 fotos · 0:24"


def test_the_empty_state_button_asks_for_photos(window: MainWindow, questions: RecordedQuestions) -> None:
    window.storyboard.empty.button.click()
    assert questions.chosen_photos == 1


def test_the_format_action_changes_the_project_through_the_controller(
    window_with_photos: MainWindow,
) -> None:
    window = window_with_photos
    window.format_action.setChecked(True)
    assert window.controller.project.output_format is OutputFormat.VERTICAL
    window.format_action.setChecked(False)
    assert window.controller.project.output_format is OutputFormat.HORIZONTAL


def test_music_and_export_actions_follow_the_project(window: MainWindow) -> None:
    """B11 enables them: music always; fitting with photos and songs; exporting with photos."""
    assert window.add_music_action.isEnabled()
    assert not window.fit_to_music_action.isEnabled()
    assert not window.export_action.isEnabled()


def test_open_has_ctrl_o_and_add_photos_does_not(window: MainWindow) -> None:
    """§1.10 reserves Ctrl+O for Obrir (B10 had given it to "+ Fotos")."""
    open_key = QKeySequence(QKeySequence.StandardKey.Open)
    assert window.open_action.shortcut() == open_key
    assert window.add_photos_action.shortcut().isEmpty()
    assert window.save_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Save)


def test_actions_follow_the_selection(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    assert not window.delete_action.isEnabled()
    window.view.select_ids(["p0001"])
    assert window.delete_action.isEnabled()
    assert window.duplicate_action.isEnabled()
    assert window.rotate_right_action.isEnabled()


def test_the_thumbnail_size_can_be_changed(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.set_thumbnail_size(ThumbnailSize.LARGE)
    assert window.view.thumbnail_size is ThumbnailSize.LARGE
    assert window.size_actions[ThumbnailSize.LARGE].isChecked()
    assert window.view.gridSize().width() > ThumbnailSize.LARGE.value


def test_undo_and_redo_follow_the_controller(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    assert window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    window.undo()
    assert window.controller.project.photos == ()
    assert window.redo_action.isEnabled()
    window.redo()
    assert len(window.controller.project.photos) == 12
