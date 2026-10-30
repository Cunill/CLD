"""The music strip, the durations in the status bar and [Ajustar a la música] (§1.7)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from passimaker.model import Music, Project, Song
from passimaker.model.commands import AddSongs, SetDefaultDuration, SetPhotoDuration
from passimaker.ui.duration_status import Balance, FitProblem, durations_of, fit_problem
from passimaker.ui.main_window import MainWindow
from passimaker.ui.music_strip import FADE_IN_MARK, FADE_OUT_MARK, SongRole
from tests.ui.helpers import RecordedQuestions, make_photos, write_song

pytestmark = pytest.mark.ui

TIMEOUT_MS = 30_000


def song(index: int, seconds: float) -> Song:
    """A song that only exists in the model (the durations do not need its file)."""
    return Song(
        id=f"s{index:02d}",
        path=Path(f"/musica/canco_{index}.mp3"),
        relative_path=None,
        original_duration_s=seconds,
    )


def add_songs_and_wait(qtbot: QtBot, window: MainWindow, paths: list[Path]) -> int:
    with qtbot.waitSignal(window.songs.finished, timeout=TIMEOUT_MS) as blocker:
        window.add_songs(paths)
    return int(blocker.args[0]) if blocker.args else 0


def labels(window: MainWindow) -> list[str]:
    model = window.music_strip.model
    return [str(model.data(model.index(row, 0))) for row in range(model.rowCount())]


def test_add_music_reads_the_songs_off_the_gui_thread(
    qtbot: QtBot, window_with_photos: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    window = window_with_photos
    questions.music = [write_song(tmp_path / "Primera.wav", 4.0), write_song(tmp_path / "Segona.wav", 6.0)]
    with qtbot.waitSignal(window.music_changed, timeout=TIMEOUT_MS):
        window.add_music_action.trigger()
    songs = window.controller.project.music.songs
    assert [s.path.name for s in songs] == ["Primera.wav", "Segona.wav"]
    assert [round(s.original_duration_s, 1) for s in songs] == [4.0, 6.0]
    assert labels(window) == [
        f"1. Primera  0:04 {FADE_IN_MARK}{FADE_OUT_MARK}",
        f"2. Segona  0:06 {FADE_IN_MARK}{FADE_OUT_MARK}",
    ]
    assert window.music_strip.view.isVisible()
    assert not window.music_strip.empty_label.isVisible()
    assert window.fit_to_music_action.isEnabled()


def test_a_file_without_sound_is_reported_in_catalan(
    qtbot: QtBot, window: MainWindow, questions: RecordedQuestions, tmp_path: Path
) -> None:
    broken = tmp_path / "trencada.mp3"
    broken.write_bytes(b"no es una canco")
    good = write_song(tmp_path / "bona.wav", 2.0)
    added = add_songs_and_wait(qtbot, window, [broken, good])
    assert added == 1
    assert [failure.path for failure in questions.song_failures] == [broken]
    assert questions.song_failures[0].message_key.startswith("ffmpeg.")


def test_songs_are_removed_and_reordered_through_the_controller(window: MainWindow) -> None:
    window.controller.execute(AddSongs((song(1, 60), song(2, 90), song(3, 30))))
    strip = window.music_strip
    strip.model.move(["s03"], 0)
    assert [s.id for s in window.controller.project.music.songs] == ["s03", "s01", "s02"]
    strip.view.setCurrentIndex(strip.model.index(1, 0))
    strip.remove_action.trigger()
    assert [s.id for s in window.controller.project.music.songs] == ["s03", "s02"]
    window.undo()
    assert [s.id for s in window.controller.project.music.songs] == ["s03", "s01", "s02"]


def test_dropping_audio_files_adds_music_and_photos_still_go_to_the_storyboard(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    track = write_song(tmp_path / "pista.flac.wav", 1.0)
    with qtbot.waitSignal(window.songs.finished, timeout=TIMEOUT_MS):
        window.receive_files([track])
    assert [s.path for s in window.controller.project.music.songs] == [track]
    assert window.controller.project.photos == ()


def test_dropping_on_the_strip_inserts_at_the_position(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    window.controller.execute(AddSongs((song(1, 60), song(2, 90))))
    track = write_song(tmp_path / "enmig.wav", 1.0)
    with qtbot.waitSignal(window.songs.finished, timeout=TIMEOUT_MS):
        window.music_strip.model.files_dropped.emit([track], 1)
    assert window.controller.project.music.songs[0].id == "s01"
    assert window.controller.project.music.songs[1].path == track


def test_keep_fitted_is_a_music_setting(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.music_strip.keep_fitted.setChecked(True)
    assert window.controller.project.music.keep_fitted
    window.undo()
    assert not window.music_strip.keep_fitted.isChecked()


def test_music_changed_is_emitted_for_the_player(qtbot: QtBot, window: MainWindow) -> None:
    with qtbot.waitSignal(window.music_changed, timeout=1_000):
        window.controller.execute(AddSongs((song(1, 60),)))


def test_missing_songs_are_drawn_in_red(window: MainWindow) -> None:
    window.controller.execute(AddSongs((song(1, 60),)))
    model = window.music_strip.model
    model.set_missing(frozenset({"s01"}))
    assert model.data(model.index(0, 0), SongRole.MISSING) is True


# --- Durations in the status bar (§1.7, "Quan la música i les fotos no duren el mateix") -----------


def test_without_music_there_is_no_warning(window_with_photos: MainWindow) -> None:
    status = window_with_photos.duration_status
    assert status.balance is Balance.NO_MUSIC
    assert not status.warning_label.isVisible()
    assert not status.fit_button.isVisible()
    assert not status.music_label.isVisible()
    assert window_with_photos.status_label.text() == "12 fotos · 0:24"


def test_music_longer_than_the_show(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.controller.execute(AddSongs((song(1, 60), song(2, 46))))  # 1:46 of music for 0:24 of photos
    status = window.duration_status
    assert status.balance is Balance.MUSIC_LONGER
    assert status.music_label.text() == "· Música 1:46"
    assert status.warning_label.text() == "⚠ La música dura 1:22 més."
    assert status.fit_button.isVisible()


def test_music_shorter_than_the_show(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    window.controller.execute(SetDefaultDuration(3.0))  # 36 s of photos
    window.controller.execute(AddSongs((song(1, 21),)))
    status = window.duration_status
    assert status.balance is Balance.MUSIC_SHORTER
    assert status.warning_label.text() == "⚠ La música s'acaba 0:15 abans."
    assert status.fit_button.isVisible()


def test_the_warning_button_fits_and_the_warning_goes_away(
    window_with_photos: MainWindow, questions: RecordedQuestions
) -> None:
    window = window_with_photos
    window.controller.execute(AddSongs((song(1, 30),)))
    window.duration_status.fit_button.click()
    assert questions.fit_checks == []  # 2.5 s per photo: within 0.4-24 s, nothing to ask.
    assert durations_of(window.controller.project).show_s == pytest.approx(30.0)
    assert window.duration_status.balance is Balance.EQUAL
    assert not window.duration_status.warning_label.isVisible()
    assert window.status_label.text() == "12 fotos · 0:30"


def test_fitting_too_many_photos_asks_first(
    window_with_photos: MainWindow, questions: RecordedQuestions
) -> None:
    window = window_with_photos
    window.controller.execute(AddSongs((song(1, 4.2),)))  # 0.35 s per photo, under 0.4 s
    questions.fit = False
    before = window.controller.project
    window.fit_to_music_action.trigger()
    assert [(c.problem, round(c.seconds_per_photo, 2)) for c in questions.fit_checks] == [
        (FitProblem.TOO_MANY_PHOTOS, 0.35)
    ]
    assert window.controller.project is before  # [Cancel·lar]
    questions.fit = True
    window.fit_to_music_action.trigger()
    assert durations_of(window.controller.project).show_s == pytest.approx(4.8)  # [Aplicar igualment]: 0.4 s


def test_fitting_does_not_ask_for_photos_between_1_and_3_s_or_beyond(
    window_with_photos: MainWindow, questions: RecordedQuestions
) -> None:
    window = window_with_photos
    window.controller.execute(AddSongs((song(1, 120.0),)))  # 10 s per photo: fine since M07
    window.fit_to_music_action.trigger()
    assert questions.fit_checks == []
    assert durations_of(window.controller.project).show_s == pytest.approx(120.0)


def test_fit_problem_tells_music_too_long() -> None:
    project = Project(slides=make_photos(4), music=Music(songs=(song(1, 120.0),)))  # 30 s per photo > 24 s
    check = fit_problem(project)
    assert check is not None
    assert check.problem is FitProblem.MUSIC_TOO_LONG
    assert not check.problem.blocks
    assert fit_problem(Project(slides=make_photos(4))) is None
    assert fit_problem(Project(slides=make_photos(4), music=Music(songs=(song(1, 60),)))) is None  # 15 s each


def test_fit_problem_counts_only_the_free_photos() -> None:
    photos = tuple(replace(p, duration_s=5.0) if i < 2 else p for i, p in enumerate(make_photos(4)))
    project = Project(slides=photos, music=Music(songs=(song(1, 10.3),)))  # 0.15 s left for 2 photos
    check = fit_problem(project)
    assert check is not None and check.problem is FitProblem.TOO_MANY_PHOTOS
    assert check.seconds_per_photo == pytest.approx(0.15)


def test_fit_problem_when_every_photo_has_a_hand_set_duration() -> None:
    photos = tuple(replace(p, duration_s=3.0) for p in make_photos(3))
    check = fit_problem(Project(slides=photos, music=Music(songs=(song(1, 60),))))
    assert check is not None and check.problem is FitProblem.ALL_FIXED and check.problem.blocks


def test_fit_problem_when_the_hand_set_photos_outlast_the_music() -> None:
    photos = tuple(replace(p, duration_s=10.0) if i == 0 else p for i, p in enumerate(make_photos(3)))
    check = fit_problem(Project(slides=photos, music=Music(songs=(song(1, 8),))))
    assert check is not None and check.problem is FitProblem.FIXED_TOO_LONG and check.problem.blocks


def test_fitting_with_every_duration_set_by_hand_only_warns(
    window_with_photos: MainWindow, questions: RecordedQuestions
) -> None:
    window = window_with_photos
    window.controller.execute(
        SetPhotoDuration(frozenset(p.id for p in window.controller.project.photos), 3.0)
    )
    window.controller.execute(AddSongs((song(1, 100.0),)))
    questions.fit = True  # even if the answer were "apply", a blocked fit changes nothing
    before = window.controller.project
    window.fit_to_music_action.trigger()
    assert [c.problem for c in questions.fit_checks] == [FitProblem.ALL_FIXED]
    assert window.controller.project is before


def test_fitting_keeps_the_hand_set_photos_and_shares_the_rest(window_with_photos: MainWindow) -> None:
    window = window_with_photos
    first = window.controller.project.photos[0].id
    window.controller.execute(SetPhotoDuration(frozenset({first}), 10.0))
    window.controller.execute(AddSongs((song(1, 32.0),)))  # 22 s left for the other 11 photos
    window.fit_to_music_action.trigger()
    project = window.controller.project
    assert project.photos[0].duration_s == 10.0
    assert project.default_duration_s == pytest.approx(2.0)
    assert durations_of(project).show_s == pytest.approx(32.0)


def test_the_boxes_of_the_fit_never_talk_about_1_to_3_seconds(qtbot: QtBot) -> None:
    from passimaker.ui.dialogs import DialogQuestions
    from passimaker.ui.duration_status import FitCheck

    real = DialogQuestions()
    qtbot.addWidget(real)
    for problem in FitProblem:
        box = real.fit_box(FitCheck(problem, 0.3))
        qtbot.addWidget(box)
        assert "1–3" not in box.text() and "1-3" not in box.text()
        assert len(box.buttons()) == (1 if problem.blocks else 2)
