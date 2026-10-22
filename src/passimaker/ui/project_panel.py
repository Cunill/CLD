"""Project panel: the settings of the whole show (§1.0, "Valors per defecte globals").

Every control sends a command to the controller (rule 2) and is refreshed from the project when
the controller says it changed, so undo and redo move the controls too (§1.13, P1). The
``_updating`` guard keeps a refresh from sending back the command it is showing.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from passimaker.model import Change, Intensity, OutputFormat, ProjectController, defaults
from passimaker.model.commands import SetDefaultDuration, SetProjectSettings
from passimaker.motion import INTENSITY_PRESETS

_INTENSITIES = (Intensity.SOFT, Intensity.MEDIUM, Intensity.STRONG)
_FORMATS = (OutputFormat.HORIZONTAL, OutputFormat.VERTICAL)
PERCENT = 100.0
"""The motion amounts are a fraction in the model and a percentage on screen (§1.0)."""


def seconds_box(allowed: defaults.Range, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(allowed.minimum, allowed.maximum)
    box.setSingleStep(allowed.step)
    box.setDecimals(1)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


def percent_box(allowed: defaults.Range, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(allowed.minimum * PERCENT, allowed.maximum * PERCENT)
    box.setSingleStep(allowed.step * PERCENT)
    box.setDecimals(0)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


class ProjectPanel(QWidget):
    """Duration, crossfade, motion, intensity and format, plus the "Avançat" group of §1.0."""

    def __init__(self, controller: ProjectController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._updating = False

        in_seconds = self.tr(" s")
        in_percent = self.tr(" %")
        self.duration = seconds_box(defaults.PHOTO_DURATION_RANGE, in_seconds)
        self.crossfade = seconds_box(defaults.CROSSFADE_RANGE, in_seconds)
        self.motion_enabled = QCheckBox(self.tr("Moviment de càmera"))
        self.intensity = QComboBox()
        for label in (self.tr("Suau"), self.tr("Mitjana"), self.tr("Marcada")):
            self.intensity.addItem(label)
        self.output_format = QComboBox()
        for label in (self.tr("Horitzontal 16:9"), self.tr("Vertical 9:16")):
            self.output_format.addItem(label)
        self.fade_from_black = seconds_box(defaults.BLACK_FADE_RANGE, in_seconds)
        self.fade_to_black = seconds_box(defaults.BLACK_FADE_RANGE, in_seconds)
        self.zoom_amount = percent_box(defaults.MOTION_AMOUNT_RANGE, in_percent)
        self.pan_amount = percent_box(defaults.MOTION_AMOUNT_RANGE, in_percent)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(self.tr("Durada per foto"), self.duration)
        form.addRow(self.tr("Fosa encadenada"), self.crossfade)
        form.addRow("", self.motion_enabled)
        form.addRow(self.tr("Intensitat del moviment"), self.intensity)
        form.addRow(self.tr("Format"), self.output_format)
        layout.addLayout(form)

        self.advanced = QGroupBox(self.tr("Avançat"))
        self.advanced.setCheckable(True)
        self.advanced.setChecked(False)
        advanced_form = QFormLayout(self.advanced)
        advanced_form.addRow(self.tr("Fosa des de negre"), self.fade_from_black)
        advanced_form.addRow(self.tr("Fosa a negre"), self.fade_to_black)
        advanced_form.addRow(self.tr("Zoom per foto"), self.zoom_amount)
        advanced_form.addRow(self.tr("Desplaçament per foto"), self.pan_amount)
        self.advanced.toggled.connect(self._show_advanced)
        layout.addWidget(self.advanced)
        layout.addStretch(1)
        self._show_advanced(False)

        self.duration.valueChanged.connect(self._on_duration)
        self.crossfade.valueChanged.connect(self._on_crossfade)
        self.motion_enabled.toggled.connect(self._on_motion_enabled)
        self.intensity.currentIndexChanged.connect(self._on_intensity)
        self.output_format.currentIndexChanged.connect(self._on_format)
        self.fade_from_black.valueChanged.connect(self._on_fade_from_black)
        self.fade_to_black.valueChanged.connect(self._on_fade_to_black)
        self.zoom_amount.valueChanged.connect(self._on_zoom)
        self.pan_amount.valueChanged.connect(self._on_pan)

        self._unsubscribe = controller.subscribe(self._on_changes)
        self.refresh()

    # --- From the project to the controls ---------------------------------------------------------

    def refresh(self) -> None:
        project = self._controller.project
        with self._quiet():
            self.duration.setValue(project.default_duration_s)
            self.crossfade.setValue(project.crossfade_s)
            self.motion_enabled.setChecked(project.motion_enabled)
            level = current_intensity(project.zoom_amount, project.pan_amount)
            self.intensity.setCurrentIndex(_INTENSITIES.index(level))
            self.output_format.setCurrentIndex(_FORMATS.index(project.output_format))
            self.fade_from_black.setValue(project.fade_from_black_s)
            self.fade_to_black.setValue(project.fade_to_black_s)
            self.zoom_amount.setValue(round(project.zoom_amount * PERCENT))
            self.pan_amount.setValue(round(project.pan_amount * PERCENT))
        self.intensity.setEnabled(project.motion_enabled)
        self.zoom_amount.setEnabled(project.motion_enabled)
        self.pan_amount.setEnabled(project.motion_enabled)

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if changes - {Change.SAVED_STATE}:
            self.refresh()

    @contextmanager
    def _quiet(self) -> Generator[None]:
        previous = self._updating
        self._updating = True
        try:
            yield
        finally:
            self._updating = previous

    def _show_advanced(self, shown: bool) -> None:
        for widget in (self.fade_from_black, self.fade_to_black, self.zoom_amount, self.pan_amount):
            widget.setVisible(shown)
        layout = self.advanced.layout()
        if isinstance(layout, QFormLayout):
            for row in range(layout.rowCount()):
                item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.setVisible(shown)

    # --- From the controls to the controller ------------------------------------------------------

    def _on_duration(self, value: float) -> None:
        self._send(SetDefaultDuration(value))

    def _on_crossfade(self, value: float) -> None:
        self._send(SetProjectSettings(crossfade_s=value))

    def _on_motion_enabled(self, enabled: bool) -> None:
        self._send(SetProjectSettings(motion_enabled=enabled))

    def _on_fade_from_black(self, value: float) -> None:
        self._send(SetProjectSettings(fade_from_black_s=value))

    def _on_fade_to_black(self, value: float) -> None:
        self._send(SetProjectSettings(fade_to_black_s=value))

    def _on_zoom(self, percent: float) -> None:
        self._send(SetProjectSettings(zoom_amount=percent / PERCENT))

    def _on_pan(self, percent: float) -> None:
        self._send(SetProjectSettings(pan_amount=percent / PERCENT))

    def _on_intensity(self, index: int) -> None:
        if 0 <= index < len(_INTENSITIES):
            self._send(SetProjectSettings(intensity=_INTENSITIES[index]))

    def _on_format(self, index: int) -> None:
        if 0 <= index < len(_FORMATS):
            self._send(SetProjectSettings(output_format=_FORMATS[index]))

    def _send(self, command: SetDefaultDuration | SetProjectSettings) -> None:
        """Rule 2: the panel never touches the project, it asks the controller to change it."""
        if not self._updating:
            self._controller.execute(command)

    def close_panel(self) -> None:
        self._unsubscribe()


def current_intensity(zoom: float, pan: float) -> Intensity:
    """The preset closest to the project amounts (the project stores the amounts, not the preset)."""
    return min(
        _INTENSITIES,
        key=lambda level: abs(INTENSITY_PRESETS[level].zoom - zoom) + abs(INTENSITY_PRESETS[level].pan - pan),
    )
