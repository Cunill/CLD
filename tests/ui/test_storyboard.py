"""Storyboard: selection, reordering by dragging, delete, duplicate and keyboard (§1.2)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt
from pytestqt.qtbot import QtBot

from passimaker.model import MotionType
from passimaker.ui.main_window import CONFIRM_DELETE_FROM, MainWindow
from passimaker.ui.photos import PHOTO_MIME, PhotoRole
from tests.ui.helpers import RecordedQuestions

pytestmark = pytest.mark.ui


def ids_of(window: MainWindow) -> list[str]:
    return [photo.id for photo in window.controller.project.photos]


def drop_photos(window: MainWindow, photo_ids: list[str], row: int) -> None:
    """Imitates letting go of a drag of these photos just before `row`."""
    data = QMimeData()
    data.setData(PHOTO_MIME, "\n".join(photo_ids).encode("utf-8"))
    window.view.model().dropMimeData(data, Qt.DropAction.MoveAction, row, 0, window.model.index(-1, -1))


def test_the_photos_are_shown_in_order_with_their_duration(window_with_photos: MainWindow) -> None:
    model = window_with_photos.model
    assert model.data(model.index(0, 0), PhotoRole.NUMBER) == 1
    assert model.data(model.index(0, 0), PhotoRole.DURATION_S) == pytest.approx(2.0)
    assert model.data(model.index(0, 0), PhotoRole.CUSTOM_DURATION) is False
    assert isinstance(model.data(model.index(0, 0), PhotoRole.MOTION_TYPE), MotionType)


def test_dragging_one_photo_moves_it(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    drop_photos(window, [before[0]], 3)
    assert ids_of(window) == [before[1], before[2], before[0], *before[3:]]


def test_dragging_several_photos_keeps_their_order(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    drop_photos(window, [before[1], before[2]], 6)
    moved = ids_of(window)
    assert moved.index(before[1]) + 1 == moved.index(before[2])
    assert moved[:1] == before[:1]
    assert moved[1:4] == [before[3], before[4], before[5]]


def test_undo_puts_the_photos_back(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    drop_photos(window, [before[0]], 5)
    assert ids_of(window) != before
    window.undo()
    assert ids_of(window) == before


def test_delete_asks_from_five_photos_on(
    window_with_photos: MainWindow, questions: RecordedQuestions
) -> None:
    window = window_with_photos
    window.view.select_ids(ids_of(window)[:4])
    window.delete_selected()
    assert questions.asked_delete == []
    assert len(window.controller.project.photos) == 8

    window.view.select_ids(ids_of(window)[:CONFIRM_DELETE_FROM])
    window.delete_selected()
    assert questions.asked_delete == [CONFIRM_DELETE_FROM]
    assert len(window.controller.project.photos) == 3


def test_a_refused_confirmation_keeps_the_photos(
    window_with_photos: MainWindow, questions: RecordedQuestions
) -> None:
    questions.delete = False
    window = window_with_photos
    window.view.select_ids(ids_of(window)[:6])
    window.delete_selected()
    assert questions.asked_delete == [6]
    assert len(window.controller.project.photos) == 12


def test_duplicate_puts_the_copy_just_after(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    window.view.select_ids([before[2]])
    window.duplicate_selected()
    after = ids_of(window)
    assert len(after) == 13
    assert after[2] == before[2]
    assert after[3] not in before
    original = window.controller.project.photos[2]
    copy = window.controller.project.photos[3]
    assert copy.path == original.path
    assert copy.motion.type != original.motion.type or original.motion.type is MotionType.NONE


def test_ctrl_left_and_ctrl_right_move_the_selection(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    window.view.select_ids([before[4]])
    window.move_selected(-1)
    assert ids_of(window)[3] == before[4]
    window.move_selected(1)
    window.move_selected(1)
    assert ids_of(window)[5] == before[4]


def test_moving_at_the_edges_does_nothing(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    window.view.select_ids([before[0]])
    window.move_selected(-1)
    assert ids_of(window) == before
    window.view.select_ids([before[-1]])
    window.move_selected(1)
    assert ids_of(window) == before


def test_select_all_selects_every_photo(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.select_all_action.trigger()
    assert len(window.view.selected_ids()) == 12


def test_the_shortcuts_are_the_ones_of_the_specification(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    shortcuts = {
        window.duplicate_action.shortcut().toString(),
        window.move_left_action.shortcut().toString(),
        window.move_right_action.shortcut().toString(),
        window.rotate_right_action.shortcut().toString(),
        window.rotate_left_action.shortcut().toString(),
    }
    assert {"Ctrl+D", "Ctrl+Left", "Ctrl+Right", "Ctrl+R", "Ctrl+Shift+R"} == shortcuts
    assert window.select_all_action.shortcut().toString() == "Ctrl+A"
    assert window.delete_action.shortcut().toString() == "Del"
    assert window.undo_action.shortcut().toString() == "Ctrl+Z"


def test_the_keyboard_duplicates_through_the_shortcut(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.setFocus()
    window.view.select_ids([ids_of(window)[0]])
    qtbot.keyClick(window.view, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert len(window.controller.project.photos) == 13


def test_rotating_asks_for_the_thumbnail_again(window_with_photos: MainWindow) -> None:
    from passimaker.model import Rotation

    window = window_with_photos
    photo_id = ids_of(window)[0]
    window.view.select_ids([photo_id])
    window.rotate_selected(Rotation.R90)
    rotated = window.controller.project.photos[0]
    assert rotated.rotation is Rotation.R90
    assert window.thumbnails.pixmap(photo_id) is None


def test_dropping_files_on_the_storyboard_reports_the_row(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    first = window.view.visualRect(window.model.index(0, 0))
    assert window.view.drop_row(QPoint(first.left() + 2, first.center().y())) == 0
    assert window.view.drop_row(QPoint(first.right() - 2, first.center().y())) == 1
    assert window.view.drop_row(QPoint(10_000, 10_000)) == -1


def test_the_view_only_asks_for_the_visible_thumbnails(window_with_photos: MainWindow, thumbnails) -> None:
    window = window_with_photos
    window.view.request_visible_thumbnails()
    assert 0 < len(set(thumbnails.requested)) <= 12


def test_a_photo_whose_file_is_missing_is_marked(window_with_photos: MainWindow) -> None:
    """§1.2: a photo that is not there gets a grey thumbnail with an icon (block B11 fills the
    list when it opens a project; here the model is asked directly)."""
    window = window_with_photos
    window.model.set_missing(frozenset({"p0002"}))
    assert window.model.data(window.model.index(1, 0), PhotoRole.MISSING) is True
    assert window.model.data(window.model.index(0, 0), PhotoRole.MISSING) is False


def test_a_thumbnail_that_fails_is_remembered(qtbot: QtBot, questions: RecordedQuestions) -> None:
    """A photo that cannot be read is not asked for again on every scroll."""
    from tests.ui.conftest import build_window
    from tests.ui.helpers import FakeThumbnailService, controller_with

    service = FakeThumbnailService(broken={"p0001"})
    window = build_window(qtbot, controller_with(4), service, questions)
    window.view.request_visible_thumbnails()
    service.wait()
    qtbot.waitUntil(lambda: window.thumbnails.failed("p0001"), timeout=10_000)
    assert window.thumbnails.pixmap("p0001") is None
    assert window.thumbnails.pixmap("p0002") is not None
    before = len(service.requested)
    window.view.request_visible_thumbnails()
    assert len(service.requested) == before
    window.close()
    service.close()


def test_the_editing_shortcuts_only_work_on_the_storyboard(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    for action in (window.delete_action, window.duplicate_action, window.select_all_action):
        assert action.shortcutContext() is Qt.ShortcutContext.WidgetWithChildrenShortcut
    # Undo and redo work from anywhere in the window.
    assert window.undo_action.shortcutContext() is Qt.ShortcutContext.WindowShortcut
