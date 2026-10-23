"""Photo panel: the settings of the selected photo or photos (§1.3, §1.5, §1.6 and P2).

Duration (and [Restablir a la general]), motion ("Automàtic" or a fixed type), [🎲 Tornar a
sortejar], fit and the two rotations. With several photos selected every control acts on all of
them; a setting on which they differ shows "Diversos" until it is changed.

Like the project panel, every control sends a command to the controller (rule 2) and is refreshed
from the project when the controller reports a change, so undo and redo move the controls too.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from passimaker.model import Change, ProjectController, defaults
from passimaker.model.commands import RerollMotions, SetPhotoDuration, SetPhotoFit, SetPhotoMotion
from passimaker.model.types import FitMode, MotionMode, MotionType, Photo, Rotation
from passimaker.ui.project_panel import seconds_box

MOTION_CHOICES: tuple[MotionType | None, ...] = (
    None,
    MotionType.ZOOM_IN,
    MotionType.ZOOM_OUT,
    MotionType.PAN_LEFT,
    MotionType.PAN_RIGHT,
    MotionType.PAN_UP,
    MotionType.PAN_DOWN,
    MotionType.COMBINED,
    MotionType.NONE,
)
"""The entries of "Moviment" (§1.5): None is "Automàtic", the others fix the motion (manual mode)."""

FIT_CHOICES = (FitMode.AUTO, FitMode.FILL, FitMode.BLUR, FitMode.BLACK)
"""The entries of "Encaix" (§1.6)."""

MIXED = -1
"""Index of a box whose photos do not agree: it shows its placeholder, "Diversos"."""
COMBO_MIN_CHARACTERS = 14


class PhotoPanel(QWidget):
    """The properties of the photos selected in the storyboard."""

    rotate_requested = Signal(object)
    """A Rotation: the window rotates the selection (it also drops the old thumbnails)."""

    def __init__(self, controller: ProjectController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._ids: tuple[str, ...] = ()
        self._updating = False

        self.title = QLabel()
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.low_resolution = QLabel(
            self.tr("Baixa resolució: el moviment es redueix perquè no es vegi pixelada.")
        )
        self.low_resolution.setWordWrap(True)
        self.duration = seconds_box(defaults.PHOTO_DURATION_RANGE, self.tr(" s"))
        self.duration_note = QLabel()
        self.reset_duration = QPushButton(self.tr("Restablir a la general"))
        self.motion = QComboBox()
        self.motion.setPlaceholderText(self.tr("Diversos"))
        for label in self._motion_labels():
            self.motion.addItem(label)
        self.reroll = QPushButton(self.tr("🎲 Tornar a sortejar"))
        self.fit = QComboBox()
        self.fit.setPlaceholderText(self.tr("Diversos"))
        for label in (
            self.tr("Automàtic"),
            self.tr("Omplir"),
            self.tr("Encaixar amb fons difuminat"),
            self.tr("Encaixar amb fons negre"),
        ):
            self.fit.addItem(label)
        self.rotate_left = QPushButton(self.tr("Girar a l'esquerra"))
        self.rotate_right = QPushButton(self.tr("Girar a la dreta"))

        for box in (self.motion, self.fit):  # the panel must fit in a narrow column
            box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(COMBO_MIN_CHARACTERS)

        duration_row = QHBoxLayout()
        duration_row.addWidget(self.duration)
        duration_row.addWidget(self.duration_note, 1)
        rotate_row = QHBoxLayout()
        rotate_row.addWidget(self.rotate_left)
        rotate_row.addWidget(self.rotate_right)
        rotate_row.addStretch(1)

        form = QFormLayout()
        form.addRow(self.tr("Durada"), duration_row)
        form.addRow("", self.reset_duration)
        form.addRow(self.tr("Moviment"), self.motion)
        form.addRow("", self.reroll)
        form.addRow(self.tr("Encaix"), self.fit)
        form.addRow(self.tr("Girar"), rotate_row)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.low_resolution)
        layout.addLayout(form)
        layout.addStretch(1)

        self.duration.valueChanged.connect(self._on_duration)
        self.reset_duration.clicked.connect(self._on_reset_duration)
        self.motion.currentIndexChanged.connect(self._on_motion)
        self.reroll.clicked.connect(self._on_reroll)
        self.fit.currentIndexChanged.connect(self._on_fit)
        self.rotate_left.clicked.connect(lambda: self.rotate_requested.emit(Rotation.R270))
        self.rotate_right.clicked.connect(lambda: self.rotate_requested.emit(Rotation.R90))

        self._unsubscribe = controller.subscribe(self._on_changes)
        self.refresh()

    def _motion_labels(self) -> list[str]:
        return [
            self.tr("Automàtic"),
            self.tr("Apropar"),
            self.tr("Allunyar"),
            self.tr("Desplaçar a l'esquerra"),
            self.tr("Desplaçar a la dreta"),
            self.tr("Desplaçar amunt"),
            self.tr("Desplaçar avall"),
            self.tr("Combinat"),
            self.tr("Cap"),
        ]

    # --- Selection ---------------------------------------------------------------------------------

    def show_photos(self, photo_ids: Sequence[str]) -> None:
        """The photos selected in the storyboard, in the order of the show."""
        self._ids = tuple(photo_ids)
        self.refresh()

    @property
    def photo_ids(self) -> tuple[str, ...]:
        return self._ids

    def photos(self) -> list[Photo]:
        wanted = set(self._ids)
        return [photo for photo in self._controller.project.photos if photo.id in wanted]

    # --- From the project to the controls ---------------------------------------------------------

    def refresh(self) -> None:
        photos = self.photos()
        self._ids = tuple(photo.id for photo in photos)
        self.setEnabled(bool(photos))
        project = self._controller.project
        with self._quiet():
            self._refresh_title(photos)
            durations = {project.photo_duration(photo) for photo in photos}
            custom = [photo for photo in photos if photo.duration_s is not None]
            self.duration.setValue(min(durations) if durations else project.default_duration_s)
            if len(durations) > 1:
                self.duration_note.setText(self.tr("(diferents)"))
            elif custom:
                self.duration_note.setText(self.tr("(personalitzada)"))
            else:
                self.duration_note.setText(self.tr("(la general)"))
            self.reset_duration.setVisible(bool(custom))
            self._refresh_motion(photos)
            fits = {photo.fit for photo in photos}
            self.fit.setCurrentIndex(FIT_CHOICES.index(fits.pop()) if len(fits) == 1 else MIXED)
        self.low_resolution.setVisible(any(photo.low_resolution for photo in photos))
        automatic = any(photo.motion.mode is MotionMode.AUTO for photo in photos)
        self.reroll.setEnabled(automatic and project.motion_enabled)
        self.reroll.setToolTip(
            self.tr("Sorteja un altre moviment")
            if automatic
            else self.tr("Només es tornen a sortejar les fotos amb el moviment automàtic")
        )
        self.motion.setEnabled(project.motion_enabled)

    def _refresh_title(self, photos: Sequence[Photo]) -> None:
        if not photos:
            self.title.setText(self.tr("Cap foto seleccionada"))
        elif len(photos) == 1:
            number = self._controller.project.photos.index(photos[0]) + 1
            self.title.setText(
                self.tr("Foto {number} · {name}").format(number=number, name=photos[0].path.name)
            )
        else:
            self.title.setText(self.tr("{count} fotos seleccionades").format(count=len(photos)))

    def _refresh_motion(self, photos: Sequence[Photo]) -> None:
        """ "Automàtic (Apropar)": in automatic mode the entry also says which type was drawn."""
        labels = self._motion_labels()
        choices = {None if photo.motion.mode is MotionMode.AUTO else photo.motion.type for photo in photos}
        drawn = {photo.motion.type for photo in photos if photo.motion.mode is MotionMode.AUTO}
        if len(drawn) == 1:
            drawn_type = next(iter(drawn))
            labels[0] = self.tr("Automàtic ({motion})").format(
                motion=labels[MOTION_CHOICES.index(drawn_type)]
            )
        self.motion.setItemText(0, labels[0])
        self.motion.setCurrentIndex(MOTION_CHOICES.index(choices.pop()) if len(choices) == 1 else MIXED)

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if changes - {Change.SAVED_STATE, Change.MUSIC}:
            self.refresh()

    @contextmanager
    def _quiet(self) -> Generator[None]:
        previous = self._updating
        self._updating = True
        try:
            yield
        finally:
            self._updating = previous

    # --- From the controls to the controller ------------------------------------------------------

    def _selection(self) -> frozenset[str]:
        return frozenset(self._ids)

    def _on_duration(self, value: float) -> None:
        self._send(SetPhotoDuration(self._selection(), value))

    def _on_reset_duration(self) -> None:
        self._send(SetPhotoDuration(self._selection(), None))

    def _on_motion(self, index: int) -> None:
        if 0 <= index < len(MOTION_CHOICES):
            self._send(SetPhotoMotion(self._selection(), MOTION_CHOICES[index]))

    def _on_reroll(self) -> None:
        """§1.5: only these photos get a new motion; the controller keeps the others as they are."""
        self._send(RerollMotions(self._selection()))

    def _on_fit(self, index: int) -> None:
        if 0 <= index < len(FIT_CHOICES):
            self._send(SetPhotoFit(self._selection(), FIT_CHOICES[index]))

    def _send(self, command: SetPhotoDuration | SetPhotoMotion | RerollMotions | SetPhotoFit) -> None:
        if not self._updating and self._ids:
            self._controller.execute(command)

    def close_panel(self) -> None:
        self._unsubscribe()
