"""M13 · Silence before and after the music: settings, undo and fit to music."""

from __future__ import annotations

import pytest

from passimaker.model import Change, defaults
from passimaker.model.commands import FitToMusic, SetMusicSettings
from passimaker.model.editing import music_span
from passimaker.model.types import Music, Project
from tests.unit.model.helpers import controller_with, song

FRAME = 1 / 30


def show_length(project: Project) -> float:
    return sum(project.photo_duration(s) for s in project.slides)


def test_new_projects_have_no_silence() -> None:
    music = Music()
    assert (music.silence_start_s, music.silence_end_s) == (0.0, 0.0) == (defaults.MUSIC_SILENCE_S,) * 2


def test_silences_are_set_clamped_and_undone() -> None:
    controller = controller_with(3, songs=[song("a", 30.0)])
    changes = controller.execute(SetMusicSettings(silence_start_s=2.5))
    assert Change.MUSIC in changes
    controller.execute(SetMusicSettings(silence_end_s=999.0))
    music = controller.project.music
    assert (music.silence_start_s, music.silence_end_s) == (2.5, defaults.MUSIC_SILENCE_RANGE.maximum)
    controller.execute(SetMusicSettings(silence_start_s=-4.0))
    assert controller.project.music.silence_start_s == 0.0
    controller.undo()
    assert controller.project.music.silence_start_s == 2.5
    controller.undo()
    assert controller.project.music.silence_end_s == 0.0
    controller.redo()
    assert controller.project.music.silence_end_s == defaults.MUSIC_SILENCE_RANGE.maximum


def test_the_same_silence_again_changes_nothing() -> None:
    controller = controller_with(1, songs=[song("a")])
    controller.execute(SetMusicSettings(silence_start_s=3.0))
    assert controller.execute(SetMusicSettings(silence_start_s=3.0)) == frozenset()


def test_music_span_adds_the_silences_only_when_there_is_music() -> None:
    assert music_span(Music(silence_start_s=2.0, silence_end_s=3.0)) == 0.0
    music = Music(silence_start_s=2.0, silence_end_s=3.0, songs=(song("a", 30.0),))
    assert music_span(music) == 35.0


def test_fit_to_music_makes_the_show_last_the_silences_plus_the_music() -> None:
    controller = controller_with(6, songs=[song("a", 40.0)])
    controller.execute(SetMusicSettings(silence_start_s=3.0, silence_end_s=5.0))
    controller.execute(FitToMusic())
    assert abs(show_length(controller.project) - 48.0) <= FRAME + 1e-9


def test_with_zero_silences_fit_to_music_is_as_before() -> None:
    controller = controller_with(6, songs=[song("a", 40.0)])
    controller.execute(FitToMusic())
    assert abs(show_length(controller.project) - 40.0) <= FRAME + 1e-9


def test_keep_fitted_follows_a_change_of_silence() -> None:
    controller = controller_with(6, songs=[song("a", 40.0)])
    controller.execute(SetMusicSettings(keep_fitted=True))
    controller.execute(SetMusicSettings(silence_end_s=8.0))
    assert abs(show_length(controller.project) - 48.0) <= FRAME + 1e-9
    controller.undo()
    assert abs(show_length(controller.project) - 40.0) <= FRAME + 1e-9


def test_without_keep_fitted_a_change_of_silence_leaves_the_photos_alone() -> None:
    controller = controller_with(4, songs=[song("a", 40.0)])
    before = show_length(controller.project)
    controller.execute(SetMusicSettings(silence_start_s=10.0))
    assert show_length(controller.project) == pytest.approx(before)
