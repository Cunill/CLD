"""M08 · The black slides in the storyboard, the photo panel and the menu."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt
from pytestqt.qtbot import QtBot

from passimaker.model import BLACK_END_ID, BLACK_START_ID, BlackSlide, BlackSlidePosition, new_project
from passimaker.model.commands import AddPhotos
from passimaker.ui.main_window import MainWindow
from passimaker.ui.photos import PHOTO_MIME, PhotoRole
from passimaker.ui.properties import PropertiesPanel
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with, make_photo

pytestmark = pytest.mark.ui


@pytest.fixture
def window(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> Iterator[MainWindow]:
    """Four photos between the two black slides of a new project."""
    made = build_window(qtbot, controller_with(4, new_project(seed=7)), thumbnails, questions)
    yield made
    made.close()


def slide_ids(window: MainWindow) -> list[str]:
    return [slide.id for slide in window.controller.project.slides]


def test_the_black_slides_are_the_first_and_last_cards(
    window: MainWindow, thumbnails: FakeThumbnailService
) -> None:
    model = window.model
    assert model.rowCount() == 6
    first, photo, last = model.index(0, 0), model.index(1, 0), model.index(5, 0)
    assert model.data(first, PhotoRole.BLACK) is True and model.data(last, PhotoRole.BLACK) is True
    assert model.data(photo, PhotoRole.BLACK) is False
    assert model.data(first, PhotoRole.NUMBER) == "Negre"
    assert model.data(first, PhotoRole.DURATION_S) == pytest.approx(2.0)
    assert [model.data(model.index(row, 0), PhotoRole.NUMBER) for row in range(1, 5)] == [1, 2, 3, 4]
    assert model.data(first, PhotoRole.PHOTO) == BlackSlide(BlackSlidePosition.START)
    assert not model.flags(first) & Qt.ItemFlag.ItemIsDragEnabled
    assert model.flags(photo) & Qt.ItemFlag.ItemIsDragEnabled
    data = model.mimeData([first, photo, last])
    assert data.data(PHOTO_MIME).toStdString() == "p0001"
    window.grab()  # the delegate draws the black cards without asking for a thumbnail
    window.view.request_visible_thumbnails()
    assert thumbnails.requested and not {BLACK_START_ID, BLACK_END_ID} & set(thumbnails.requested)


def test_drops_land_between_the_black_slides(window: MainWindow) -> None:
    def drop(ids: list[str], row: int) -> None:
        data = QMimeData()
        data.setData(PHOTO_MIME, "\n".join(ids).encode("utf-8"))
        window.model.dropMimeData(data, Qt.DropAction.MoveAction, row, 0, window.model.index(-1, -1))

    drop(["p0004"], 0)  # before the black slide of the start: just after it
    assert slide_ids(window) == [BLACK_START_ID, "p0004", "p0001", "p0002", "p0003", BLACK_END_ID]
    drop(["p0004"], 6)  # after the black slide of the end: just before it
    assert slide_ids(window) == [BLACK_START_ID, "p0001", "p0002", "p0003", "p0004", BLACK_END_ID]
    drop([BLACK_START_ID], 3)  # a black slide is never moved
    assert slide_ids(window)[0] == BLACK_START_ID

    first = window.view.visualRect(window.model.index(0, 0))
    assert window.view.drop_row(QPoint(first.left() + 2, first.center().y())) == 1
    assert window.view.drop_row(QPoint(10_000, 10_000)) == 5
    assert window.model.photo_index(1) == 0 and window.model.photo_index(5) == 4
    assert window.model.photo_index(-1) == 4


def test_a_new_project_shows_the_empty_state_and_a_photo_shows_the_storyboard(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> None:
    window = build_window(qtbot, controller_with(0, new_project(seed=7)), thumbnails, questions)
    assert window.storyboard.currentWidget() is window.storyboard.empty
    window.controller.execute(AddPhotos((make_photo(1),)))
    assert window.storyboard.currentWidget() is window.storyboard.view
    window.close()


def test_delete_removes_a_black_slide_and_the_menu_puts_it_back(window: MainWindow) -> None:
    assert not window.black_start_action.isEnabled() and not window.black_end_action.isEnabled()
    window.view.select_ids([BLACK_START_ID, "p0002"])
    window.delete_selected()
    assert slide_ids(window) == ["p0001", "p0003", "p0004", BLACK_END_ID]
    assert window.black_start_action.isEnabled() and not window.black_end_action.isEnabled()
    window.black_start_action.trigger()
    assert slide_ids(window)[0] == BLACK_START_ID
    assert not window.black_start_action.isEnabled()
    window.undo()
    assert slide_ids(window)[0] == "p0001"
    window.redo()
    assert slide_ids(window)[0] == BLACK_START_ID


def test_moving_a_photo_with_the_keyboard_stops_at_the_black_slides(window: MainWindow) -> None:
    window.view.select_ids(["p0001"])
    window.move_selected(-1)
    assert slide_ids(window)[1] == "p0001"
    window.move_selected(1)
    assert slide_ids(window)[1:3] == ["p0002", "p0001"]
    window.view.select_ids([BLACK_END_ID])
    assert not window.move_left_action.isEnabled()
    assert window.delete_action.isEnabled()


def test_the_photo_panel_of_a_black_slide_only_has_the_duration(window: MainWindow) -> None:
    panel = window.photo_panel
    window.view.select_ids([BLACK_END_ID])
    assert window.properties.currentIndex() == PropertiesPanel.PHOTO
    assert panel.title.text() == "Negre al final"
    assert panel.duration.value() == pytest.approx(2.0)
    assert panel.duration.isVisibleTo(panel)
    assert not panel.motion.isVisibleTo(panel) and not panel.fit.isVisibleTo(panel)
    assert not panel.rotate_left.isVisibleTo(panel) and not panel.reroll.isVisibleTo(panel)
    panel.duration.setValue(4.5)
    assert window.controller.project.black_end == BlackSlide(BlackSlidePosition.END, 4.5)
    # 2 + 4 x 2 + 4.5 = 14.5 s
    assert window.status_label.text() == "4 fotos · 0:14"

    window.view.select_ids([BLACK_START_ID, BLACK_END_ID])
    assert panel.title.text() == "Negre a l'inici i al final"
    window.view.select_ids(["p0001"])
    assert panel.motion.isVisibleTo(panel) and panel.fit.isVisibleTo(panel)
    assert "Foto 1" in panel.title.text()


def test_selecting_a_black_slide_shows_it_in_the_preview(window: MainWindow) -> None:
    window.view.select_ids([BLACK_END_ID])
    assert window.player_panel._shown_photo == BLACK_END_ID
