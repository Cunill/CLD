"""B1: every editing command, value clamping and the change kinds reported to observers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from passimaker import timeline
from passimaker.model import Change, ProjectController, new_project
from passimaker.model.commands import (
    AddPhotos,
    AddSongs,
    DuplicatePhotos,
    FitToMusic,
    MovePhotos,
    MoveSongs,
    RemovePhotos,
    RemoveSongs,
    RerollMotions,
    RotatePhotos,
    SetDefaultDuration,
    SetMusicSettings,
    SetPhotoDuration,
    SetPhotoFit,
    SetPhotoMotion,
    SetProjectSettings,
    SortPhotos,
    UpdateSong,
)
from passimaker.model.editing import music_duration, natural_key, visible_durations
from passimaker.model.types import (
    Fade,
    FitMode,
    Intensity,
    MotionMode,
    MotionType,
    OutputFormat,
    Photo,
    Project,
    ResolvedFit,
    Rotation,
)
from passimaker.motion import INTENSITY_PRESETS
from tests.unit.model.helpers import controller_with, ids, photo, photos, song

# --- Photos ---------------------------------------------------------------------------------------


def test_added_photos_get_a_motion_and_go_at_the_end_or_at_the_index() -> None:
    controller = controller_with(3)
    changes = controller.execute(AddPhotos((photo("new1"), photo("new2")), index=1))
    assert {Change.PHOTOS, Change.TIMING, Change.MOTION} <= changes
    assert ids(controller.project) == ["p000", "new1", "new2", "p001", "p002"]
    controller.execute(AddPhotos((photo("last"),)))
    assert ids(controller.project)[-1] == "last"
    assert all(p.motion.type is not MotionType.NONE for p in controller.project.photos)


def test_first_draw_follows_rule_4() -> None:
    controller = controller_with(8)
    types = [p.motion.type for p in controller.project.photos]
    assert types[0] is MotionType.ZOOM_IN
    assert types[-1] is MotionType.ZOOM_OUT


def test_adding_photos_does_not_change_the_type_of_the_others() -> None:
    controller = controller_with(6)
    before = {p.id: p.motion.type for p in controller.project.photos}
    controller.execute(AddPhotos(photos(4, prefix="n")))
    after = {p.id: p.motion.type for p in controller.project.photos}
    assert all(after[pid] == kind for pid, kind in before.items())


def test_repeated_ids_are_made_unique() -> None:
    controller = controller_with(2)
    controller.execute(AddPhotos((photo("p000"), photo("p000"))))
    assert ids(controller.project) == ["p000", "p001", "p000~2", "p000~3"]


def test_added_photo_durations_are_clamped() -> None:
    controller = controller_with(0)
    controller.execute(AddPhotos((photo("a", duration=0.2), photo("b", duration=99))))
    assert [p.duration_s for p in controller.project.photos] == [0.4, 24.0]


def test_remove_photos() -> None:
    controller = controller_with(4)
    changes = controller.execute(RemovePhotos(frozenset({"p000", "p003"})))
    assert ids(controller.project) == ["p001", "p002"]
    assert {Change.PHOTOS, Change.TIMING} <= changes


@pytest.mark.parametrize(
    ("moved", "target", "expected"),
    [
        (("p000",), 3, ["p001", "p002", "p000", "p003", "p004"]),
        (("p004",), 0, ["p004", "p000", "p001", "p002", "p003"]),
        (("p001", "p003"), 5, ["p000", "p002", "p004", "p001", "p003"]),
        (("p003", "p001"), 0, ["p001", "p003", "p000", "p002", "p004"]),  # block keeps the list order
        (("p001", "p002"), 2, ["p000", "p001", "p002", "p003", "p004"]),  # dropped on itself
        (("p000",), 99, ["p001", "p002", "p003", "p004", "p000"]),  # target clamped
    ],
)
def test_move_photos(moved: tuple[str, ...], target: int, expected: list[str]) -> None:
    controller = controller_with(5)
    controller.execute(MovePhotos(moved, target))
    assert ids(controller.project) == expected


def test_reordering_never_draws_again() -> None:
    controller = controller_with(6)
    before = {p.id: (p.motion.type, p.motion.draw_count) for p in controller.project.photos}
    changes = controller.execute(MovePhotos(("p000",), 6))
    after = {p.id: (p.motion.type, p.motion.draw_count) for p in controller.project.photos}
    assert after == before
    assert Change.PHOTOS in changes


def test_duplicate_goes_after_the_original_with_a_different_motion() -> None:
    controller = controller_with(4)
    controller.execute(SetPhotoDuration(frozenset({"p001"}), 2.7))
    controller.execute(SetPhotoFit(frozenset({"p001"}), FitMode.BLACK))
    controller.execute(DuplicatePhotos(("p001", "p002")))
    project = controller.project
    assert ids(project) == ["p000", "p001", "p001~2", "p002", "p002~2", "p003"]
    by_id = {p.id: p for p in project.photos}
    original, copy = by_id["p001"], by_id["p001~2"]
    assert copy.duration_s == 2.7 and copy.fit is FitMode.BLACK and copy.path == original.path
    assert (copy.motion.type, copy.motion.start, copy.motion.end) != (
        original.motion.type,
        original.motion.start,
        original.motion.end,
    )
    assert by_id["p002~2"].motion.type != by_id["p002"].motion.type


def test_sort_by_name_uses_natural_order() -> None:
    controller = ProjectController()
    names = ["IMG_10.jpg", "img_2.jpg", "IMG_1.jpg"]
    controller.execute(AddPhotos(tuple(photo(f"x{i}", name=n) for i, n in enumerate(names))))
    controller.execute(SortPhotos(by_date=False))
    assert [p.path.name for p in controller.project.photos] == ["IMG_1.jpg", "img_2.jpg", "IMG_10.jpg"]
    assert natural_key("a2") < natural_key("A10")


def test_sort_by_date_puts_undated_photos_last() -> None:
    controller = ProjectController()
    controller.execute(
        AddPhotos(
            (
                photo("late", taken=datetime(2024, 5, 2)),
                photo("none", name="a.jpg"),
                photo("early", taken=datetime(2023, 1, 1)),
            )
        )
    )
    controller.execute(SortPhotos(by_date=True))
    assert ids(controller.project) == ["early", "late", "none"]


# --- Durations ------------------------------------------------------------------------------------


def test_default_duration_is_clamped_and_affects_photos_without_their_own() -> None:
    controller = controller_with(3)
    controller.execute(SetPhotoDuration(frozenset({"p000"}), 2.5))
    assert controller.execute(SetDefaultDuration(70.0)) >= {Change.TIMING}
    project = controller.project
    assert project.default_duration_s == 24.0
    assert [project.photo_duration(p) for p in project.photos] == [2.5, 24.0, 24.0]
    controller.execute(SetDefaultDuration(0.0))
    assert controller.project.default_duration_s == 0.4


def test_photo_duration_is_clamped_and_can_be_reset() -> None:
    controller = controller_with(2)
    controller.execute(SetPhotoDuration(frozenset({"p000", "p001"}), 0.1))
    assert [p.duration_s for p in controller.project.photos] == [0.4, 0.4]
    controller.execute(SetPhotoDuration(frozenset({"p001"}), None))
    assert [p.duration_s for p in controller.project.photos] == [0.4, None]


def test_duration_change_keeps_the_motion_types() -> None:
    # Photos are visible at least 1 s (FULL_MOTION_MIN_S), so the windows do not depend on the
    # duration; the motion is only rebuilt, never drawn again.
    controller = controller_with(5)
    before = {p.id: p.motion for p in controller.project.photos}
    controller.execute(SetPhotoDuration(frozenset({"p002"}), 1.0))
    controller.execute(SetProjectSettings(crossfade_s=0.5))
    assert {p.id: p.motion for p in controller.project.photos} == before


def test_motion_amount_change_rebuilds_windows_but_keeps_the_type() -> None:
    controller = controller_with(5)
    before = {p.id: p.motion for p in controller.project.photos}
    changes = controller.execute(SetProjectSettings(zoom_amount=0.15, pan_amount=0.15))
    after = {p.id: p.motion for p in controller.project.photos}
    assert Change.MOTION in changes
    assert all(
        after[pid].type == m.type and after[pid].draw_count == m.draw_count for pid, m in before.items()
    )
    assert all(after[pid] != m for pid, m in before.items() if m.type is not MotionType.NONE)


def test_visible_durations_follow_the_crossfade_rule() -> None:
    project = Project(slides=(photo("a", duration=1.0), photo("b", duration=3.0), photo("c", duration=3.0)))
    # a-b: min(1.0, 0.5, 1.5) = 0.5; b-c: min(1.0, 1.5, 1.5) = 1.0
    assert visible_durations(project) == pytest.approx([1.25, 3.0 + 0.25 + 0.5, 3.5])
    assert visible_durations(Project()) == []
    assert visible_durations(Project(slides=(photo("solo"),))) == [2.0]


# --- Fit and motion -------------------------------------------------------------------------------


def test_fit_change_resolves_the_new_fit() -> None:
    controller = controller_with(3)
    controller.execute(SetPhotoFit(frozenset({"p001"}), FitMode.BLUR))
    by_id = {p.id: p for p in controller.project.photos}
    assert by_id["p001"].fit is FitMode.BLUR
    assert by_id["p001"].motion.resolved_fit is ResolvedFit.BLUR
    assert by_id["p000"].motion.resolved_fit is ResolvedFit.FILL


def test_manual_motion_and_back_to_automatic() -> None:
    controller = controller_with(4)
    controller.execute(SetPhotoMotion(frozenset({"p001", "p002"}), MotionType.PAN_LEFT))
    chosen = [p for p in controller.project.photos if p.id in {"p001", "p002"}]
    assert all(p.motion.mode is MotionMode.MANUAL and p.motion.type is MotionType.PAN_LEFT for p in chosen)
    controller.execute(SetPhotoMotion(frozenset({"p001"}), None))
    by_id = {p.id: p for p in controller.project.photos}
    assert by_id["p001"].motion.mode is MotionMode.AUTO
    assert by_id["p002"].motion.mode is MotionMode.MANUAL


def test_reroll_increments_the_draw_count_and_changes_the_motion() -> None:
    controller = controller_with(6)
    before = {p.id: p.motion for p in controller.project.photos}
    assert controller.execute(RerollMotions(frozenset({"p002"}))) == {Change.MOTION, Change.SAVED_STATE}
    after = {p.id: p.motion for p in controller.project.photos}
    assert after["p002"].draw_count == before["p002"].draw_count + 1
    assert after["p002"].type != before["p002"].type
    assert all(after[pid] == m for pid, m in before.items() if pid != "p002")


def test_reroll_all_respects_manual_photos() -> None:
    controller = controller_with(6)
    controller.execute(SetPhotoMotion(frozenset({"p003"}), MotionType.ZOOM_OUT))
    manual = next(p for p in controller.project.photos if p.id == "p003").motion
    controller.execute(RerollMotions(None))
    project = controller.project
    assert next(p for p in project.photos if p.id == "p003").motion == manual
    assert all(p.motion.draw_count == 1 for p in project.photos if p.id != "p003")


def test_a_new_random_motion_also_frees_a_manual_photo() -> None:
    """M05 ("Nou moviment a l'atzar"): the chosen photos get a new motion even if it was fixed by hand."""
    controller = controller_with(6)
    controller.execute(SetPhotoMotion(frozenset({"p003"}), MotionType.ZOOM_OUT))
    before = {p.id: p.motion for p in controller.project.photos}
    undo_steps = len(controller._undo)  # pyright: ignore[reportPrivateUsage]
    controller.execute(RerollMotions(frozenset({"p003"})))
    after = {p.id: p.motion for p in controller.project.photos}
    assert after["p003"].mode is MotionMode.AUTO
    assert after["p003"].draw_count == before["p003"].draw_count + 1
    assert after["p003"].type != MotionType.ZOOM_OUT
    assert all(after[pid] == m for pid, m in before.items() if pid != "p003")
    assert len(controller._undo) == undo_steps + 1  # pyright: ignore[reportPrivateUsage]
    controller.undo()
    assert next(p for p in controller.project.photos if p.id == "p003").motion == before["p003"]


def test_rotation_is_relative_and_swaps_the_size() -> None:
    controller = ProjectController()
    controller.execute(AddPhotos((photo("a", 4000, 3000),)))
    controller.execute(RotatePhotos(frozenset({"a"}), Rotation.R90))
    rotated = controller.project.photos[0]
    assert (rotated.rotation, rotated.width, rotated.height) == (Rotation.R90, 3000, 4000)
    assert rotated.motion.resolved_fit is ResolvedFit.BLUR  # a portrait photo in a landscape video
    controller.execute(RotatePhotos(frozenset({"a"}), Rotation.R270))
    back = controller.project.photos[0]
    assert (back.rotation, back.width, back.height) == (Rotation.R0, 4000, 3000)
    assert back.motion.resolved_fit is ResolvedFit.FILL


def test_output_format_change_keeps_the_motion_types() -> None:
    controller = controller_with(6)
    before = [p.motion.type for p in controller.project.photos]
    changes = controller.execute(SetProjectSettings(output_format=OutputFormat.VERTICAL))
    assert Change.MOTION in changes
    project = controller.project
    assert project.output_format is OutputFormat.VERTICAL
    for old, new in zip(before, project.photos, strict=True):
        # 4:3 photos now sit on a blurred background, which only allows zoom motions.
        assert new.motion.resolved_fit is ResolvedFit.BLUR
        if old in (MotionType.ZOOM_IN, MotionType.ZOOM_OUT):
            assert new.motion.type is old


def test_the_4_3_format_fills_4_3_photos_and_keeps_the_black_slides() -> None:
    """M10: the fit is resolved again for the new proportion; black slides have no size or fit."""
    controller = ProjectController(new_project(seed=7))
    controller.execute(AddPhotos(photos(4)))  # 4000x3000
    black = (controller.project.black_start, controller.project.black_end)
    controller.execute(SetProjectSettings(output_format=OutputFormat.VERTICAL_3_4))
    assert all(p.motion.resolved_fit is ResolvedFit.BLUR for p in controller.project.photos)
    controller.execute(SetProjectSettings(output_format=OutputFormat.HORIZONTAL_4_3))
    project = controller.project
    assert all(p.motion.resolved_fit is ResolvedFit.FILL for p in project.photos)
    assert (project.black_start, project.black_end) == black
    assert project.slides[0] is black[0] and project.slides[-1] is black[1]
    controller.undo()
    assert controller.project.output_format is OutputFormat.VERTICAL_3_4


def test_project_settings_are_clamped() -> None:
    controller = ProjectController()
    controller.execute(
        SetProjectSettings(
            crossfade_s=9.0, fade_from_black_s=-1.0, fade_to_black_s=8.0, zoom_amount=1.0, pan_amount=-1
        )
    )
    project = controller.project
    assert (project.crossfade_s, project.fade_from_black_s, project.fade_to_black_s) == (1.5, 0.0, 5.0)
    assert (project.zoom_amount, project.pan_amount) == (0.20, 0.0)


def test_intensity_preset_sets_both_amounts() -> None:
    controller = controller_with(3)
    changes = controller.execute(SetProjectSettings(intensity=Intensity.STRONG))
    preset = INTENSITY_PRESETS[Intensity.STRONG]
    assert (controller.project.zoom_amount, controller.project.pan_amount) == (preset.zoom, preset.pan)
    assert Change.MOTION in changes


def test_change_kinds_of_project_settings() -> None:
    controller = ProjectController()
    assert Change.SETTINGS in controller.execute(SetProjectSettings(name="x"))
    assert Change.TIMING in controller.execute(SetProjectSettings(fade_to_black_s=3.0))
    assert Change.MOTION in controller.execute(SetProjectSettings(motion_enabled=False))


# --- Music ----------------------------------------------------------------------------------------


def test_add_move_remove_songs() -> None:
    controller = ProjectController()
    assert Change.MUSIC in controller.execute(AddSongs((song("a"), song("b"), song("c"))))
    controller.execute(AddSongs((song("a"),), index=0))
    assert [s.id for s in controller.project.music.songs] == ["a~2", "a", "b", "c"]
    controller.execute(MoveSongs(("a~2",), 4))
    assert [s.id for s in controller.project.music.songs] == ["a", "b", "c", "a~2"]
    controller.execute(RemoveSongs(frozenset({"b", "a~2"})))
    assert [s.id for s in controller.project.music.songs] == ["a", "c"]


def test_song_settings_are_clamped() -> None:
    controller = ProjectController()
    controller.execute(AddSongs((song("a", 100.0),)))
    changed = song(
        "a",
        100.0,
        trim_start_s=150.0,
        trim_end_s=20.0,
        fade_in=Fade(True, 30.0),
        fade_out=Fade(False, -2.0),
        volume=9.0,
    )
    assert Change.MUSIC in controller.execute(UpdateSong(changed))
    stored = controller.project.music.songs[0]
    assert (stored.trim_start_s, stored.trim_end_s) == (100.0, 100.0)  # the start never passes the end
    assert stored.fade_in == Fade(True, 10.0) and stored.fade_out == Fade(False, 0.0)
    assert stored.volume == 1.5


def test_update_of_an_unknown_song_changes_nothing() -> None:
    controller = ProjectController()
    assert controller.execute(UpdateSong(song("ghost"))) == frozenset()


def test_music_settings_are_clamped() -> None:
    controller = ProjectController()
    controller.execute(SetMusicSettings(master_volume=4.0, normalize=False))
    music = controller.project.music
    assert music.master_volume == 1.0 and not music.normalize


def test_music_duration_uses_the_trims() -> None:
    project = Project()
    music = project.music.__class__(
        songs=(song("a", 100.0, trim_start_s=10.0, trim_end_s=70.0), song("b", 30.0))
    )
    assert music_duration(music) == 90.0


# --- Fit to music (uses timeline.fit_to_music from block B2) --------------------------------------


@pytest.mark.usefixtures("fake_fit")
def test_fit_to_music_keeps_the_photos_set_by_hand_and_the_default_marks() -> None:
    controller = controller_with(4, songs=[song("a", 12.0)])
    controller.execute(SetPhotoDuration(frozenset({"p000"}), 3.0))
    # p000 is fixed at 3 s; the other three share the remaining 9 s
    changes = controller.execute(FitToMusic())
    assert Change.TIMING in changes
    project = controller.project
    assert [p.duration_s for p in project.photos] == [3.0, None, None, None]  # still default
    assert project.default_duration_s == pytest.approx(3.0)
    assert sum(project.photo_duration(p) for p in project.photos) == pytest.approx(12.0)


@pytest.mark.usefixtures("fake_fit")
def test_fit_to_music_does_not_touch_a_hand_set_duration_even_above_3_s() -> None:
    controller = controller_with(4, songs=[song("a", 30.0)])
    controller.execute(SetPhotoDuration(frozenset({"p000"}), 10.0))
    controller.execute(FitToMusic())
    project = controller.project
    assert project.photos[0].duration_s == 10.0
    assert project.default_duration_s == pytest.approx(20 / 3)


@pytest.mark.usefixtures("fake_fit")
def test_fit_to_music_with_every_duration_set_by_hand_does_nothing() -> None:
    controller = controller_with(3, songs=[song("a", 30.0)])
    controller.execute(SetPhotoDuration(frozenset({"p000", "p001", "p002"}), 4.0))
    assert controller.execute(FitToMusic()) == frozenset()


def test_fit_to_music_when_the_music_does_not_cover_the_fixed_photos_does_nothing() -> None:
    controller = controller_with(3, songs=[song("a", 6.0)])
    controller.execute(SetPhotoDuration(frozenset({"p000", "p001"}), 5.0))  # 10 s fixed > 6 s of music
    assert controller.execute(FitToMusic()) == frozenset()


def test_fit_to_music_in_the_real_timeline_respects_hand_set_durations() -> None:
    controller = controller_with(6, songs=[song("a", 40.0)])
    controller.execute(SetPhotoDuration(frozenset({"p001"}), 15.0))
    controller.execute(FitToMusic())
    project = controller.project
    assert project.photos[1].duration_s == 15.0
    assert abs(sum(project.photo_duration(p) for p in project.photos) - 40.0) <= 1 / 30 + 1e-9
    assert project.default_duration_s == pytest.approx(5.0)


@pytest.mark.usefixtures("fake_fit")
def test_fit_to_music_without_music_or_photos_does_nothing() -> None:
    assert ProjectController().execute(FitToMusic()) == frozenset()
    assert controller_with(3).execute(FitToMusic()) == frozenset()


@pytest.mark.usefixtures("fake_fit")
def test_keep_fitted_refits_when_photos_or_songs_change() -> None:
    controller = controller_with(4, songs=[song("a", 10.0)])
    controller.execute(SetMusicSettings(keep_fitted=True))
    assert controller.project.default_duration_s == pytest.approx(2.5)
    controller.execute(AddPhotos(photos(1, prefix="n")))
    assert controller.project.default_duration_s == pytest.approx(2.0)
    controller.execute(AddSongs((song("b", 5.0),)))
    assert controller.project.default_duration_s == pytest.approx(3.0)
    controller.execute(RemovePhotos(frozenset({"n000"})))
    assert controller.project.default_duration_s == pytest.approx(3.75)  # 15 s / 4 photos, no 3 s limit now


@pytest.mark.usefixtures("fake_fit")
def test_keep_fitted_keeps_the_hand_set_photos_when_photos_are_added() -> None:
    controller = controller_with(4, songs=[song("a", 20.0)])
    controller.execute(SetPhotoDuration(frozenset({"p000"}), 8.0))
    controller.execute(SetMusicSettings(keep_fitted=True))
    assert controller.project.default_duration_s == pytest.approx(4.0)  # 12 s among 3 photos
    controller.execute(AddPhotos(photos(1, prefix="n")))
    assert controller.project.photos[0].duration_s == 8.0
    assert controller.project.default_duration_s == pytest.approx(3.0)  # 12 s among 4 photos


def test_fit_to_music_with_the_real_timeline() -> None:
    """Integration with block B2 (timeline.fit_to_music)."""
    controller = controller_with(10, songs=[song("a", 25.0)])
    controller.execute(FitToMusic())
    project = controller.project
    total = sum(project.photo_duration(p) for p in project.photos)
    assert abs(total - 25.0) <= 1 / 30 + 1e-9
    assert timeline.compute_timeline(project).total_duration_s == pytest.approx(total, abs=1 / 30)


def test_visible_durations_match_the_timeline() -> None:
    """The motion draw uses the same visible spans as the timeline (block B2)."""
    durations = [1.0, 3.0, 1.4, 2.2, 2.0, 1.0]
    project = Project(slides=tuple(photo(f"q{i}", duration=d) for i, d in enumerate(durations)))
    line = timeline.compute_timeline(project)
    spans = [s.visible_end - s.visible_start for s in line.slots]
    assert spans == pytest.approx(visible_durations(project))


def test_unrelated_photo_fields_are_kept() -> None:
    controller = ProjectController()
    original = Photo(
        "a", Path("/x/a.jpg"), Path("a.jpg"), 4000, 3000, exif_orientation=6, low_resolution=True
    )
    controller.execute(AddPhotos((original,)))
    stored = controller.project.photos[0]
    assert (stored.path, stored.relative_path, stored.exif_orientation, stored.low_resolution) == (
        original.path,
        original.relative_path,
        6,
        True,
    )
