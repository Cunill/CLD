"""Photo panel and the global motion actions (block B14, §1.3, §1.5, §1.6 and P2)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from passimaker.model.commands import SetPhotoDuration, SetPhotoMotion
from passimaker.model.types import FitMode, MotionMode, MotionType, Rotation
from passimaker.ui.main_window import MainWindow
from passimaker.ui.photo_panel import FIT_CHOICES, MIXED, MOTION_CHOICES
from passimaker.ui.properties import PropertiesPanel
from tests.ui.test_player_panel import time_to_next_frame, wait_frame

pytestmark = pytest.mark.ui


def photo(window: MainWindow, photo_id: str):
    return next(p for p in window.controller.project.photos if p.id == photo_id)


def test_selecting_a_photo_opens_its_tab(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    assert not window.properties.isTabEnabled(PropertiesPanel.PHOTO)
    window.view.select_ids(["p0004"])
    assert window.properties.currentIndex() == PropertiesPanel.PHOTO
    assert window.photo_panel.photo_ids == ("p0004",)
    assert "Foto 4" in window.photo_panel.title.text()
    window.view.clearSelection()
    assert window.properties.currentIndex() == PropertiesPanel.PROJECT
    assert not window.properties.isTabEnabled(PropertiesPanel.PHOTO)


def test_the_duration_is_custom_and_can_be_reset(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.view.select_ids(["p0002"])
    assert not panel.reset_duration.isVisibleTo(panel)
    panel.duration.setValue(2.7)
    assert photo(window, "p0002").duration_s == pytest.approx(2.7)
    assert photo(window, "p0003").duration_s is None
    assert panel.reset_duration.isVisibleTo(panel)
    panel.reset_duration.click()
    assert photo(window, "p0002").duration_s is None
    assert panel.duration.value() == pytest.approx(window.controller.project.default_duration_s)


def test_values_out_of_range_cannot_be_entered(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.view.select_ids(["p0002"])
    panel.duration.setValue(99.0)
    assert photo(window, "p0002").duration_s == pytest.approx(24.0)
    panel.duration.setValue(0.1)
    assert photo(window, "p0002").duration_s == pytest.approx(0.4)
    # Typed: "70" is not accepted by a box from 0,4 to 24.
    panel.duration.lineEdit().selectAll()
    qtbot.keyClicks(panel.duration.lineEdit(), "70")
    qtbot.keyClick(panel.duration.lineEdit(), Qt.Key.Key_Return)
    assert 0.4 <= (photo(window, "p0002").duration_s or 0) <= 24.0


def test_the_numbers_use_the_decimal_comma(qtbot: QtBot, window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.view.select_ids(["p0002"])
    panel.duration.setValue(2.5)
    assert panel.duration.text() == "2,5 s"
    panel.duration.lineEdit().selectAll()
    qtbot.keyClicks(panel.duration.lineEdit(), "1,8")
    qtbot.keyClick(panel.duration.lineEdit(), Qt.Key.Key_Return)
    assert photo(window, "p0002").duration_s == pytest.approx(1.8)
    assert window.panel.crossfade.text() == "1,0 s"


def test_the_motion_box_fixes_the_motion(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.view.select_ids(["p0005"])
    assert panel.motion.currentIndex() == 0  # Automàtic
    assert panel.motion.itemText(0).startswith("Automàtic (")
    panel.motion.setCurrentIndex(MOTION_CHOICES.index(MotionType.ZOOM_OUT))
    chosen = photo(window, "p0005").motion
    assert (chosen.mode, chosen.type) == (MotionMode.MANUAL, MotionType.ZOOM_OUT)
    assert panel.reroll.isEnabled()  # M05: also for a motion fixed by hand
    assert panel.reroll.text() == "🎲 Nou moviment a l'atzar"
    panel.reroll.click()
    again = photo(window, "p0005").motion
    assert again.mode is MotionMode.AUTO
    assert again.draw_count == chosen.draw_count + 1
    assert panel.motion.currentIndex() == 0  # Automàtic


def test_the_fit_box_changes_the_fit(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.view.select_ids(["p0003"])
    panel.fit.setCurrentIndex(FIT_CHOICES.index(FitMode.BLACK))
    assert photo(window, "p0003").fit is FitMode.BLACK
    panel.fit.setCurrentIndex(FIT_CHOICES.index(FitMode.AUTO))
    assert photo(window, "p0003").fit is FitMode.AUTO


@pytest.mark.parametrize(
    ("change", "photo_id"),
    [
        ("motion", "p0003"),
        ("fit", "p0003"),
        ("duration", "p0003"),
        ("reroll", "p0003"),
        ("rotate", "p0003"),
    ],
)
def test_every_control_changes_the_preview(
    qtbot: QtBot, window_with_photos: MainWindow, change: str, photo_id: str
) -> None:
    window = window_with_photos
    panel = window.photo_panel
    preview = window.player_panel
    if change == "motion":  # from a known motion, so that the new one is surely different
        window.controller.execute(SetPhotoMotion(frozenset({photo_id}), MotionType.ZOOM_IN))
    window.view.select_ids([photo_id])
    before = wait_frame(qtbot, preview).copy()
    actions = {
        "motion": lambda: panel.motion.setCurrentIndex(MOTION_CHOICES.index(MotionType.PAN_UP)),
        "fit": lambda: panel.fit.setCurrentIndex(FIT_CHOICES.index(FitMode.BLACK)),
        # 2,8 s: at 1,2 s the crossfade shrinks in proportion and the photo start shows the same frame.
        "duration": lambda: panel.duration.setValue(2.8),
        "reroll": panel.reroll.click,
        "rotate": panel.rotate_right.click,
    }
    time_to_next_frame(qtbot, preview, actions[change])
    after = wait_frame(qtbot, preview)
    assert after != before, f"{change}: the preview did not change"


def test_several_photos_are_edited_at_once(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.controller.execute(SetPhotoMotion(frozenset({"p0002"}), MotionType.PAN_LEFT))
    window.view.select_ids(["p0001", "p0002", "p0003"])
    assert "3 fotos" in panel.title.text()
    assert panel.motion.currentIndex() == MIXED  # "Diversos": one is manual, two automatic
    panel.duration.setValue(2.4)
    panel.fit.setCurrentIndex(FIT_CHOICES.index(FitMode.BLUR))
    for photo_id in ("p0001", "p0002", "p0003"):
        edited = photo(window, photo_id)
        assert edited.duration_s == pytest.approx(2.4)
        assert edited.fit is FitMode.BLUR
    assert photo(window, "p0004").duration_s is None
    assert panel.fit.currentIndex() == FIT_CHOICES.index(FitMode.BLUR)
    window.photo_panel.rotate_left.click()
    assert {photo(window, pid).rotation for pid in ("p0001", "p0002", "p0003")} == {Rotation.R270}


def test_drawing_again_one_photo_does_not_change_the_others(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    before = {p.id: p.motion for p in window.controller.project.photos}
    window.view.select_ids(["p0006"])
    window.photo_panel.reroll.click()
    after = {p.id: p.motion for p in window.controller.project.photos}
    assert after["p0006"] != before["p0006"]
    assert after["p0006"].draw_count == before["p0006"].draw_count + 1
    assert {k: v for k, v in after.items() if k != "p0006"} == {
        k: v for k, v in before.items() if k != "p0006"
    }


def test_drawing_all_again_respects_the_manual_ones(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.controller.execute(SetPhotoMotion(frozenset({"p0002", "p0007"}), MotionType.PAN_DOWN))
    before = {p.id: p.motion for p in window.controller.project.photos}
    window.panel.reroll_all.click()
    after = {p.id: p.motion for p in window.controller.project.photos}
    for photo_id, motion in before.items():
        if photo_id in ("p0002", "p0007"):
            assert after[photo_id] == motion
        else:
            assert after[photo_id].draw_count == motion.draw_count + 1
    # The same from the menu.
    window.reroll_all_action.trigger()
    assert photo(window, "p0002").motion == before["p0002"]


def test_reset_all_to_automatic(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    assert not window.reset_motions_action.isEnabled()
    window.controller.execute(SetPhotoMotion(frozenset({"p0002", "p0007"}), MotionType.NONE))
    untouched = photo(window, "p0003").motion
    assert window.reset_motions_action.isEnabled()
    window.reset_motions_action.trigger()
    assert all(p.motion.mode is MotionMode.AUTO for p in window.controller.project.photos)
    assert photo(window, "p0003").motion == untouched
    assert not window.reset_motions_action.isEnabled()


def test_undo_moves_the_controls_back(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.view.select_ids(["p0002"])
    panel.fit.setCurrentIndex(FIT_CHOICES.index(FitMode.FILL))
    panel.duration.setValue(1.5)
    window.undo()
    assert panel.duration.value() == pytest.approx(window.controller.project.default_duration_s)
    window.undo()
    assert panel.fit.currentIndex() == FIT_CHOICES.index(FitMode.AUTO)
    assert window.controller.can_redo


def test_removing_the_selected_photo_takes_its_tab_away(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.select_ids(["p0002"])
    window.delete_selected()
    assert not window.properties.isTabEnabled(PropertiesPanel.PHOTO)
    assert window.properties.currentIndex() == PropertiesPanel.PROJECT


def test_without_camera_motion_the_motion_controls_are_disabled(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.view.select_ids(["p0002"])
    window.panel.motion_enabled.setChecked(False)
    assert not window.photo_panel.motion.isEnabled()
    assert not window.photo_panel.reroll.isEnabled()
    assert not window.panel.reroll_all.isEnabled()


def test_enter_gives_the_duration_shown_to_photos_with_different_durations(
    window_with_photos: MainWindow,
) -> None:
    window = window_with_photos
    panel = window.photo_panel
    window.controller.execute(SetPhotoDuration(frozenset({"p0002"}), 2.8))
    window.view.select_ids(["p0001", "p0002"])
    shown = panel.duration.value()
    assert panel.duration_note.text() == "(diferents)"
    panel.duration.lineEdit().returnPressed.emit()  # typing the value shown and pressing Enter
    assert photo(window, "p0001").duration_s == pytest.approx(shown)
    assert photo(window, "p0002").duration_s == pytest.approx(shown)
