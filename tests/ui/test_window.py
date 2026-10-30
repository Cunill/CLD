"""The main window: layout of §1.0, empty state, status bar and the actions of the toolbar."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QSplitterHandle
from pytestqt.qtbot import QtBot

from passimaker.model import OutputFormat
from passimaker.model.commands import AddPhotos
from passimaker.ui.delegate import ThumbnailSize
from passimaker.ui.main_window import MIN_PREVIEW_HEIGHT, MIN_PROPERTIES_HEIGHT, MainWindow, PreviewSplitter
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with
from tests.unit.model.helpers import photos

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


# --- M11: the line between the preview and the properties --------------------------------------


def _handle(window: MainWindow) -> tuple[PreviewSplitter, QSplitterHandle]:
    splitter = window.preview_splitter
    return splitter, splitter.handle(1)


def test_the_preview_line_is_thick_and_has_the_vertical_cursor(window: MainWindow) -> None:
    splitter, handle = _handle(window)
    assert splitter.handleWidth() >= 8
    assert handle.cursor().shape() == Qt.CursorShape.SizeVerCursor


def test_the_preview_line_has_a_wide_travel(window: MainWindow) -> None:
    splitter, _ = _handle(window)
    total = sum(splitter.sizes())
    splitter.moveSplitter(0, 1)
    top, bottom = splitter.sizes()
    assert top == MIN_PREVIEW_HEIGHT and top < total // 4
    splitter.moveSplitter(total, 1)
    top, bottom = splitter.sizes()
    assert bottom == MIN_PROPERTIES_HEIGHT and top > total // 2


def test_dragging_the_line_with_the_mouse(window: MainWindow, qtbot: QtBot) -> None:
    splitter, handle = _handle(window)
    before = splitter.sizes()[0]
    centre = handle.rect().center()
    qtbot.mousePress(handle, Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseMove(handle, centre + QPoint(0, 80))
    qtbot.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=centre + QPoint(0, 80))
    assert splitter.sizes()[0] > before


def test_the_position_is_remembered_between_sessions(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> None:
    first = build_window(qtbot, controller_with(0), thumbnails, questions)
    first.preview_splitter.moveSplitter(0, 1)
    saved = first.preview_splitter.saved_fraction()
    assert saved is not None and saved < 0.3
    first.close()
    second = build_window(qtbot, controller_with(0), thumbnails, questions)
    sizes = second.preview_splitter.sizes()
    assert sizes[0] / sum(sizes) == pytest.approx(saved, abs=0.03)
    second.close()


def test_a_double_click_restores_the_default_position(window: MainWindow, qtbot: QtBot) -> None:
    splitter, handle = _handle(window)
    default = splitter.sizes()[0] / sum(splitter.sizes())
    splitter.moveSplitter(0, 1)
    qtbot.mouseDClick(handle, Qt.MouseButton.LeftButton)
    sizes = splitter.sizes()
    assert sizes[0] / sum(sizes) == pytest.approx(0.6, abs=0.03)
    assert default == pytest.approx(0.6, abs=0.03)


def test_the_shuffle_action_mixes_the_photos_and_can_be_undone(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = [p.id for p in window.controller.project.photos]
    assert window.shuffle_action.isEnabled()
    window.shuffle_action.trigger()
    assert [p.id for p in window.controller.project.photos] != before
    window.undo_action.trigger()
    assert [p.id for p in window.controller.project.photos] == before


def test_the_shuffle_action_needs_two_photos(window: MainWindow) -> None:
    assert not window.shuffle_action.isEnabled()
    window.controller.execute(AddPhotos(photos(1)))
    assert not window.shuffle_action.isEnabled()
    window.controller.execute(AddPhotos(photos(1, prefix="q")))
    assert window.shuffle_action.isEnabled()
