"""Durations in the status bar and [Ajustar a la música] (§1.0 and §1.7).

"124 fotos · 4:30 · Música 5:52 ⚠ La música dura 1:22 més [Ajustar]": the length of the music next
to the length of the show, and a discreet warning when they differ. Before fitting, ``fit_problem``
tells whether the photos could not reach the music within their limits (or whether there is nothing to
fit), so the window can ask or warn before applying it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from passimaker.model import Project
from passimaker.model.editing import fixed_durations, music_duration
from passimaker.timeline import fit_to_music
from passimaker.timeline.types import FitBlock
from passimaker.ui.formatting import clock

WARNING_MARK = "⚠"


class Balance(Enum):
    """How the music compares with the show (table "Quan la música i les fotos no duren el mateix")."""

    NO_MUSIC = "no_music"
    EQUAL = "equal"
    MUSIC_LONGER = "music_longer"
    MUSIC_SHORTER = "music_shorter"


@dataclass(frozen=True, slots=True)
class Durations:
    show_s: float
    music_s: float

    @property
    def difference_s(self) -> float:
        """Music minus show; positive when the music lasts longer."""
        return self.music_s - self.show_s

    @property
    def balance(self) -> Balance:
        if self.music_s <= 0:
            return Balance.NO_MUSIC
        # Under half a second the two clocks of the status bar show the same time.
        if round(abs(self.difference_s)) == 0:
            return Balance.EQUAL
        return Balance.MUSIC_LONGER if self.difference_s > 0 else Balance.MUSIC_SHORTER


def durations_of(project: Project) -> Durations:
    """The show is the sum of the photo durations, as in "124 fotos · 4:30" (§1.3)."""
    show = sum(project.photo_duration(photo) for photo in project.photos)
    return Durations(show, music_duration(project.music))


class FitProblem(Enum):
    TOO_MANY_PHOTOS = "too_many_photos"
    MUSIC_TOO_LONG = "music_too_long"
    ALL_FIXED = "all_fixed"
    """Every duration was set by hand: nothing to fit (decision 0014)."""
    FIXED_TOO_LONG = "fixed_too_long"
    """The durations set by hand already last as long as the music or longer."""

    @property
    def blocks(self) -> bool:
        """True when the fit cannot be applied at all (no "apply anyway")."""
        return self in (FitProblem.ALL_FIXED, FitProblem.FIXED_TOO_LONG)


@dataclass(frozen=True, slots=True)
class FitCheck:
    problem: FitProblem
    seconds_per_photo: float


def fit_problem(project: Project) -> FitCheck | None:
    """§1.7: None when the free photos can reach the music within 0.4-24 s; otherwise what the warning says.

    ``seconds_per_photo`` is what each free photo would last (the music left after the fixed ones).
    """
    durations = [project.photo_duration(photo) for photo in project.photos]
    target = music_duration(project.music)
    if not durations or target <= 0:
        return None
    fixed = fixed_durations(project)
    result = fit_to_music(durations, target, fixed=fixed)
    if result.blocked is not None:
        problem = FitProblem.ALL_FIXED if result.blocked is FitBlock.ALL_FIXED else FitProblem.FIXED_TOO_LONG
        return FitCheck(problem, 0.0)
    if not result.warning:
        return None
    free = fixed.count(False)
    fixed_total = math.fsum(d for d, f in zip(durations, fixed, strict=True) if f)
    per_photo = (target - fixed_total) / free
    problem = FitProblem.MUSIC_TOO_LONG if result.achieved_total_s < target else FitProblem.TOO_MANY_PHOTOS
    return FitCheck(problem, per_photo)


class DurationStatus(QWidget):
    """ "Música 5:52 ⚠ La música dura 1:22 més [Ajustar a la música]" in the status bar."""

    fit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.music_label = QLabel()
        self.warning_label = QLabel()
        self.fit_button = QPushButton(self.tr("Ajustar a la música"))
        self.fit_button.setFlat(True)
        self.fit_button.clicked.connect(self.fit_requested)
        layout.addWidget(self.music_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.fit_button)
        self.balance = Balance.NO_MUSIC

    def refresh(self, project: Project) -> None:
        times = durations_of(project)
        self.balance = times.balance
        has_music = times.balance is not Balance.NO_MUSIC
        self.music_label.setVisible(has_music)
        self.music_label.setText(self.tr("· Música {duration}").format(duration=clock(times.music_s)))
        gap = clock(abs(times.difference_s))
        if times.balance is Balance.MUSIC_LONGER:
            text = self.tr("La música dura {gap} més.").format(gap=gap)
        elif times.balance is Balance.MUSIC_SHORTER:
            text = self.tr("La música s'acaba {gap} abans.").format(gap=gap)
        else:
            text = ""
        warned = bool(text) and bool(project.photos)
        self.warning_label.setText(f"{WARNING_MARK} {text}" if warned else "")
        self.warning_label.setVisible(warned)
        self.fit_button.setVisible(warned)
