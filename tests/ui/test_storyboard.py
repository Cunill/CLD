"""Storyboard: selection, reordering by dragging, delete, duplicate and keyboard (§1.2)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QPalette
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from passimaker.model import MotionType
from passimaker.ui.main_window import CONFIRM_DELETE_FROM, MainWindow
from passimaker.ui.photos import PHOTO_MIME, PhotoRole
from passimaker.ui.storyboard import SPACING
from tests.ui.conftest import build_window, controller_with
from tests.ui.helpers import RecordedQuestions

pytestmark = pytest.mark.ui


def ids_of(window: MainWindow) -> list[str]:
    return [photo.id for photo in window.controller.project.photos]


def drop_photos(window: MainWindow, photo_ids: list[str], row: int) -> None:
    """Imitates letting go of a drag of these photos just before `row`."""
    data = QMimeData()
    data.setData(PHOTO_MIME, "\n".join(photo_ids).encode("utf-8"))
    window.view.model().dropMimeData(data, Qt.DropAction.MoveAction, row, 0, window.model.index(-1, -1))


_MOVE, _LEFT, _NO_KEYS = Qt.DropAction.MoveAction, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier


def drag_over(window: MainWindow, photo_ids: list[str], to: QPoint) -> tuple[QMimeData, bool, Qt.DropAction]:
    """Imitates what Qt delivers to the grid while photos are dragged over it: enter, then move to `to`.

    Returns the dragged data, whether the move was accepted and with which action (M04: the grid used
    to refuse every drag of its own photos, and the tests that only imitate letting go did not notice).
    """
    view = window.view
    data = view.model().mimeData([window.model.index(window.model.row_of(pid), 0) for pid in photo_ids])
    QApplication.sendEvent(view.viewport(), QDragEnterEvent(to, _MOVE, data, _LEFT, _NO_KEYS))
    move = QDragMoveEvent(to, _MOVE, data, _LEFT, _NO_KEYS)
    QApplication.sendEvent(view.viewport(), move)
    return data, move.isAccepted(), move.dropAction()


def drag_photos_with_the_mouse(
    window: MainWindow, photo_ids: list[str], to: QPoint
) -> tuple[bool, Qt.DropAction]:
    """The whole gesture: drag over the grid to `to` and let go there."""
    data, accepted, action = drag_over(window, photo_ids, to)
    QApplication.sendEvent(window.view.viewport(), QDropEvent(QPointF(to), _MOVE, data, _LEFT, _NO_KEYS))
    return accepted, action


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


def test_dragging_with_the_mouse_moves_the_photo(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    cell = window.view.visualRect(window.model.index(4, 0))
    accepted, action = drag_photos_with_the_mouse(
        window, [before[0]], QPoint(cell.left() + 3, cell.center().y())
    )
    assert accepted
    assert action == Qt.DropAction.MoveAction
    assert ids_of(window) == [*before[1:4], before[0], *before[4:]]


def test_dragging_with_the_mouse_to_the_right_half_of_a_photo_puts_it_after(
    window_with_photos: MainWindow,
) -> None:
    window = window_with_photos
    before = ids_of(window)
    cell = window.view.visualRect(window.model.index(6, 0))
    drag_photos_with_the_mouse(window, [before[1], before[2]], QPoint(cell.right() - 3, cell.center().y()))
    assert ids_of(window) == [before[0], *before[3:7], before[1], before[2], *before[7:]]


def test_a_line_shows_where_the_dragged_photos_will_go(window_with_photos: MainWindow, qtbot: QtBot) -> None:
    window = window_with_photos
    view = window.view
    window.show()
    qtbot.waitExposed(window)
    ids = ids_of(window)
    cell = view.visualRect(window.model.index(3, 0))
    drag_over(window, [ids[0]], QPoint(cell.left() + 3, cell.center().y()))
    line = view.insertion_line()
    assert line is not None
    assert line.height() > 0 and line.width() <= 4
    assert cell.left() - SPACING - 4 <= line.center().x() <= cell.left() + 2
    # The line is drawn: the pixel in its middle has the highlight colour.
    image = view.viewport().grab().toImage()
    colour = view.palette().color(QPalette.ColorRole.Highlight)
    assert image.pixelColor(line.center()).rgb() == colour.rgb()
    QApplication.sendEvent(view.viewport(), QDragLeaveEvent())
    assert view.insertion_line() is None
    assert ids_of(window) == ids  # leaving the grid moves nothing


def test_letting_go_between_two_photos_puts_it_between_them(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = ids_of(window)
    left_cell = window.view.visualRect(window.model.index(3, 0))
    right_cell = window.view.visualRect(window.model.index(4, 0))
    assert right_cell.left() - left_cell.right() > 1  # there is a gap
    gap = QPoint((left_cell.right() + right_cell.left()) // 2, left_cell.center().y())
    drag_photos_with_the_mouse(window, [before[0]], gap)
    assert ids_of(window) == [*before[1:4], before[0], *before[4:]]


def test_letting_go_after_the_end_of_a_line_of_the_grid_puts_it_after_its_last_photo(
    window_with_photos: MainWindow,
) -> None:
    window = window_with_photos
    view = window.view
    before = ids_of(window)
    columns = view.viewport().width() // view.gridSize().width()
    last_of_line = view.visualRect(window.model.index(columns - 1, 0))
    empty = QPoint(view.viewport().width() - 2, last_of_line.center().y())
    assert not view.indexAt(empty).isValid()
    drag_photos_with_the_mouse(window, [before[0]], empty)
    assert ids_of(window).index(before[0]) == columns - 1  # just after the line's last photo


def test_the_line_stays_on_the_line_of_the_grid_under_the_cursor(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    view = window.view
    columns = view.viewport().width() // view.gridSize().width()
    last_of_line = view.visualRect(window.model.index(columns - 1, 0))
    drag_over(window, [ids_of(window)[0]], QPoint(last_of_line.right() - 3, last_of_line.center().y()))
    line = view.insertion_line()
    assert line is not None
    assert line.top() == last_of_line.top()  # not at the start of the next line
    assert last_of_line.right() <= line.left() <= last_of_line.right() + SPACING
    QApplication.sendEvent(view.viewport(), QDragLeaveEvent())


def test_letting_go_where_the_photo_was_changes_nothing(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.controller.mark_saved()
    project = window.controller.project
    own = window.view.visualRect(window.model.index(2, 0))
    drag_photos_with_the_mouse(window, [ids_of(window)[2]], QPoint(own.left() + 3, own.center().y()))
    assert window.controller.project is project  # no command: nothing to undo
    assert not window.controller.has_unsaved_changes


def test_dragging_near_the_bottom_edge_scrolls_the_grid(qtbot: QtBot, thumbnails, questions) -> None:
    window = build_window(qtbot, controller_with(200), thumbnails, questions)
    window.show()
    qtbot.waitExposed(window)
    view = window.view
    bar = view.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == 0
    near_bottom = QPoint(view.viewport().width() // 2, view.viewport().height() - 2)
    drag_over(window, [ids_of(window)[0]], near_bottom)
    qtbot.waitUntil(lambda: bar.value() > 0, timeout=2000)
    QApplication.sendEvent(view.viewport(), QDragLeaveEvent())
    window.close()


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
