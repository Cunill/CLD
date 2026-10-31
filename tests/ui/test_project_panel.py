"""Project panel: every control reaches the model through the controller (rule 2)."""

from __future__ import annotations

import pytest

from passimaker.model import Intensity, OutputFormat, ProjectController, defaults
from passimaker.model.commands import Command
from passimaker.motion import INTENSITY_PRESETS
from passimaker.ui.main_window import MainWindow
from passimaker.ui.project_panel import PERCENT, current_intensity

pytestmark = pytest.mark.ui


class _Spy(ProjectController):
    """A controller that remembers the commands it was given."""

    def __init__(self) -> None:
        super().__init__()
        self.commands: list[Command] = []

    def execute(self, command: Command) -> frozenset:
        self.commands.append(command)
        return super().execute(command)


def test_every_change_goes_through_a_command(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    panel = window.panel
    panel.duration.setValue(2.5)
    assert window.controller.project.default_duration_s == pytest.approx(2.5)
    panel.crossfade.setValue(1.4)
    assert window.controller.project.crossfade_s == pytest.approx(1.4)
    panel.motion_enabled.setChecked(False)
    assert window.controller.project.motion_enabled is False
    panel.output_format.setCurrentIndex(3)
    assert window.controller.project.output_format is OutputFormat.VERTICAL
    panel.output_format.setCurrentIndex(2)
    assert window.controller.project.output_format is OutputFormat.HORIZONTAL_4_3


def test_the_commands_are_the_ones_of_the_contract(qtbot, thumbnails, questions) -> None:
    from tests.ui.conftest import build_window

    controller = _Spy()
    window = build_window(qtbot, controller, thumbnails, questions)
    window.panel.duration.setValue(1.5)
    window.panel.crossfade.setValue(0.8)
    names = [type(command).__name__ for command in controller.commands]
    assert names == ["SetDefaultDuration", "SetProjectSettings"]
    window.close()


def test_the_intensity_sets_both_amounts(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.panel.intensity.setCurrentIndex(2)
    project = window.controller.project
    assert project.zoom_amount == pytest.approx(INTENSITY_PRESETS[Intensity.STRONG].zoom)
    assert project.pan_amount == pytest.approx(INTENSITY_PRESETS[Intensity.STRONG].pan)
    assert current_intensity(project.zoom_amount, project.pan_amount) is Intensity.STRONG


def test_the_advanced_amounts_are_percentages(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.panel.advanced.setChecked(True)
    window.panel.zoom_amount.setValue(15)
    assert window.controller.project.zoom_amount == pytest.approx(0.15)
    assert window.panel.zoom_amount.maximum() == pytest.approx(defaults.MOTION_AMOUNT_RANGE.maximum * PERCENT)


def test_the_ranges_come_from_defaults(window: MainWindow) -> None:
    panel = window.panel
    assert panel.duration.minimum() == pytest.approx(defaults.PHOTO_DURATION_RANGE.minimum)
    assert panel.duration.maximum() == pytest.approx(defaults.PHOTO_DURATION_RANGE.maximum)
    assert panel.crossfade.minimum() == pytest.approx(defaults.CROSSFADE_RANGE.minimum)
    assert panel.fade_to_black.maximum() == pytest.approx(defaults.BLACK_FADE_RANGE.maximum)


def test_a_value_out_of_range_is_clamped(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.panel.duration.setValue(99.0)
    assert window.controller.project.default_duration_s == pytest.approx(
        defaults.PHOTO_DURATION_RANGE.maximum
    )


def test_undo_moves_the_controls_back(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.panel.duration.setValue(3.0)
    window.undo()
    assert window.panel.duration.value() == pytest.approx(defaults.PHOTO_DURATION_S)


def test_the_advanced_group_starts_folded(window: MainWindow) -> None:
    assert not window.panel.advanced.isChecked()
    assert not window.panel.zoom_amount.isVisible()


def test_turning_off_the_motion_disables_the_intensity(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.panel.motion_enabled.setChecked(False)
    assert not window.panel.intensity.isEnabled()
    window.panel.motion_enabled.setChecked(True)
    assert window.panel.intensity.isEnabled()


def test_the_format_box_lists_the_six_formats_and_follows_the_project(window: MainWindow) -> None:
    """M10: three landscape proportions, then three portrait ones; undo shows the previous one."""
    box = window.panel.output_format
    labels = [box.itemText(i) for i in range(box.count())]
    assert labels == [
        "Horitzontal 16:9",
        "Horitzontal 3:2",
        "Horitzontal 4:3",
        "Vertical 9:16",
        "Vertical 2:3",
        "Vertical 3:4",
    ]
    for index, output_format in enumerate(OutputFormat):
        box.setCurrentIndex(index)
        assert window.controller.project.output_format is output_format
    window.controller.undo()
    assert box.currentIndex() == 4
    window.format_actions[OutputFormat.HORIZONTAL_3_2].trigger()
    assert box.currentIndex() == 1
