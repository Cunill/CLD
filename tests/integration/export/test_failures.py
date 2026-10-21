"""B9: errors, cancellation and leftovers. An export that does not finish leaves no file."""

from __future__ import annotations

import errno
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from passimaker.audio import MixedAudioSource
from passimaker.common import CancelToken, RGBImage
from passimaker.export import (
    ERROR_DISK_FULL,
    ERROR_FAILED,
    ERROR_MISSING_FILES,
    ERROR_NO_PHOTOS,
    ERROR_WRITE,
    ExportStatus,
    checks,
    export_project,
    missing_files,
    pipeline,
    power,
)
from passimaker.ffmpeg import ERROR_DISK_FULL as FFMPEG_DISK_FULL
from passimaker.ffmpeg import FfmpegError, FfmpegVideoWriter
from passimaker.model import Project
from passimaker.render import Compositor
from tests.integration.export.conftest import ProgressLog, ffprobe, make_project

TWO_PHOTOS = ("ratio_4x3.jpg", "ratio_16x9.jpg")
EIGHT_PHOTOS = (
    "ratio_4x3.jpg",
    "ratio_3x2.jpg",
    "ratio_16x9.jpg",
    "ratio_9x16.jpg",
    "ratio_1x1.jpg",
    "pano_3x1.jpg",
    "photo.heic",
    "orient_6.jpg",
)
MAX_CANCEL_S = 2.0


@pytest.fixture
def temp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The system temporary folder, for this test only (to see what the export leaves there)."""
    folder = tmp_path / "temporal"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


@pytest.fixture
def small(fixture_files: dict[str, Path], tmp_path: Path) -> Project:
    return make_project(fixture_files, tmp_path / "fotos", TWO_PHOTOS, ("tone_440.wav",))


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "sortida"
    folder.mkdir()
    return folder


def _leftovers(*folders: Path) -> list[Path]:
    return [path for folder in folders for path in folder.iterdir()]


# --- Before starting ------------------------------------------------------------------------------


def test_a_project_without_photos_is_not_exported(out_dir: Path) -> None:
    result = export_project(Project(), out_dir / "buit.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_NO_PHOTOS)
    assert _leftovers(out_dir) == []


def test_missing_files_are_listed_and_nothing_is_exported(small: Project, out_dir: Path) -> None:
    gone_photo = small.photos[1].path
    gone_photo.unlink()
    song = small.music.songs[0]
    gone_song = song.path.with_name("no hi és.mp3")
    project = replace(small, music=replace(small.music, songs=(replace(song, path=gone_song), song)))
    assert missing_files(project) == (gone_photo, gone_song)
    result = export_project(project, out_dir / "vídeo.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_MISSING_FILES)
    assert _leftovers(out_dir) == []


def test_a_destination_folder_that_does_not_exist(small: Project, tmp_path: Path) -> None:
    result = export_project(small, tmp_path / "no existeix" / "vídeo.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_WRITE)
    assert not (tmp_path / "no existeix").exists()


def test_not_enough_space_is_found_before_starting(
    small: Project, out_dir: Path, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checks, "free_bytes", lambda folder: 10 * 1024 * 1024)
    result = export_project(small, out_dir / "vídeo.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_DISK_FULL)
    assert _leftovers(out_dir, temp_dir) == []


# --- While exporting ------------------------------------------------------------------------------


def test_disk_full_while_encoding(
    small: Project, out_dir: Path, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The encoder reports a full disk after 10 frames: clear error, no partial file, awake state cleared."""

    class FillsUp:
        def __init__(self, writer: FfmpegVideoWriter) -> None:
            self.writer = writer
            self.frames = 0

        def write(self, frame: RGBImage) -> None:
            self.frames += 1
            if self.frames > 10:
                raise FfmpegError(FFMPEG_DISK_FULL, "simulat")
            self.writer.write(frame)

        def close(self) -> None:
            self.writer.close()

        def abort(self) -> None:
            self.writer.abort()

    real_open = pipeline.open_encoder
    monkeypatch.setattr(pipeline, "open_encoder", lambda *args: FillsUp(real_open(*args)))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    states: list[int] = []
    monkeypatch.setattr(power, "set_execution_state", lambda flags: states.append(flags) or True)
    result = export_project(small, out_dir / "ple.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_DISK_FULL)
    assert _leftovers(out_dir, temp_dir) == []
    assert states == [power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED, power.ES_CONTINUOUS]


def test_disk_full_while_writing_the_audio(
    small: Project, out_dir: Path, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(self: MixedAudioSource, dest: Path, *args: object) -> None:
        dest.write_bytes(b"RIFF")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(MixedAudioSource, "render_wav", full)
    result = export_project(small, out_dir / "ple.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_DISK_FULL)
    assert _leftovers(out_dir, temp_dir) == []


def test_an_unexpected_error_leaves_nothing(
    small: Project, out_dir: Path, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: Compositor, t: float, width: int, height: int, *, sentinel: bool = False) -> RGBImage:
        if t > 0.5:
            raise ValueError("error de prova")
        return original(self, t, width, height, sentinel=sentinel)

    original = Compositor.frame_at
    monkeypatch.setattr(Compositor, "frame_at", broken)
    result = export_project(small, out_dir / "error.mp4")
    assert (result.status, result.reason_key) == (ExportStatus.ERROR, ERROR_FAILED)
    assert _leftovers(out_dir, temp_dir) == []


def test_cancelled_before_starting(small: Project, out_dir: Path, temp_dir: Path) -> None:
    cancel = CancelToken()
    cancel.cancel()
    result = export_project(small, out_dir / "res.mp4", cancel=cancel)
    assert result.status is ExportStatus.CANCELLED
    assert _leftovers(out_dir, temp_dir) == []


@pytest.mark.lent
def test_cancel_at_half_stops_quickly_and_leaves_nothing(
    fixture_files: dict[str, Path], tmp_path: Path, out_dir: Path, temp_dir: Path
) -> None:
    project = make_project(fixture_files, tmp_path / "fotos", EIGHT_PHOTOS, ("tone_880.mp3",))
    cancel = CancelToken()
    cancelled_at: list[float] = []
    log = ProgressLog()

    def progress(fraction: float, remaining: float | None) -> None:
        log(fraction, remaining)
        if fraction >= 0.5 and not cancelled_at:
            cancelled_at.append(time.monotonic())
            cancel.cancel()

    result = export_project(project, out_dir / "cancel·lat.mp4", progress=progress, cancel=cancel)
    stopped = time.monotonic() - cancelled_at[0]
    assert result.status is ExportStatus.CANCELLED
    assert stopped < MAX_CANCEL_S
    assert _leftovers(out_dir, temp_dir) == []


@pytest.mark.lent
def test_cancel_from_another_thread(
    fixture_files: dict[str, Path], tmp_path: Path, out_dir: Path, temp_dir: Path
) -> None:
    """As the interface does it: the export runs on a worker thread and [Cancel·lar] comes from another."""
    project = make_project(fixture_files, tmp_path / "fotos", EIGHT_PHOTOS)
    cancel = CancelToken()
    half = threading.Event()
    results: list[object] = []

    def progress(fraction: float, remaining: float | None) -> None:
        if fraction >= 0.5:
            half.set()

    def work() -> None:
        results.append(export_project(project, out_dir / "fil.mp4", progress=progress, cancel=cancel))

    worker = threading.Thread(target=work)
    worker.start()
    assert half.wait(120)
    started = time.monotonic()
    cancel.cancel()
    worker.join(MAX_CANCEL_S + 5)
    assert not worker.is_alive()
    assert time.monotonic() - started < MAX_CANCEL_S
    assert [getattr(r, "status", None) for r in results] == [ExportStatus.CANCELLED]
    assert _leftovers(out_dir, temp_dir) == []


@pytest.mark.lent
def test_an_existing_video_is_replaced(small: Project, out_dir: Path, temp_dir: Path) -> None:
    """The interface asks before; the export itself replaces the file (only at the end)."""
    dest = out_dir / "ja existeix.mp4"
    dest.write_bytes(b"un altre fitxer")
    result = export_project(small, dest)
    assert result.status is ExportStatus.DONE
    assert ffprobe(dest).video["codec_name"] == "h264"
    assert _leftovers(out_dir) == [dest]
    assert _leftovers(temp_dir) == []
