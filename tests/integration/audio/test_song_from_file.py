"""song_from_file: the song rule shared by the interface and the command line (M05)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from passimaker.audio import song_from_file
from passimaker.ffmpeg import ERROR_NO_AUDIO, FfmpegError
from tests.ui.helpers import write_song


def test_a_song_gets_its_length_and_an_absolute_path(tmp_path: Path) -> None:
    path = write_song(tmp_path / "música" / "Cançó.wav", 2.0)
    song = song_from_file(path, "s01")
    assert song.id == "s01"
    assert song.path == path.absolute()
    assert song.original_duration_s == pytest.approx(2.0, abs=0.05)
    assert song.trim_start_s == 0 and song.trim_end_s is None


def test_a_file_without_sound_is_refused(tmp_path: Path) -> None:
    """The command line used to accept it (only the window checked it): now both refuse it."""
    picture = tmp_path / "imatge.png"
    Image.new("RGB", (16, 16)).save(picture)
    with pytest.raises(FfmpegError) as error:
        song_from_file(picture, "s01")
    assert error.value.message_key == ERROR_NO_AUDIO
