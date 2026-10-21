"""B7: open_encoder (pipe, abort, errors) and extract_frames with the real FFmpeg."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from passimaker import ffmpeg
from passimaker.common import RGBImage
from passimaker.ffmpeg import _video

FAST = ffmpeg.EncoderSettings(preset="ultrafast")


def gray_frame(width: int, height: int, level: int) -> RGBImage:
    return np.full((height, width, 3), level, dtype=np.uint8)


def run_with_watchdog(task: Callable[[], None], seconds: float) -> None:
    """Runs task on a thread; fails (instead of hanging the suite) if it takes longer than `seconds`."""
    errors: list[BaseException] = []

    def target() -> None:
        try:
            task()
        except BaseException as error:  # re-raised below on the test thread
            errors.append(error)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), f"bloqueig: la tasca no ha acabat en {seconds} s"
    if errors:
        raise errors[0]


def test_encoded_video_has_the_right_format(fixture_files: dict[str, Path], tmp_path: Path) -> None:
    dest = tmp_path / "passi.mp4"
    writer = ffmpeg.open_encoder(dest, 320, 240, fixture_files["tone_440.wav"], FAST)
    for n in range(8 * 30):
        writer.write(gray_frame(320, 240, n % 256))
    writer.close()
    info = ffmpeg.probe(dest)
    assert info.has_video and info.has_audio
    assert (info.width, info.height) == (320, 240)
    assert info.sample_rate == 48000 and info.channels == 2
    assert abs(info.duration_s - 8.0) <= 0.05


def test_default_settings_follow_the_specification() -> None:
    args = _video.encoder_args(
        Path("ffmpeg"), Path("v.mp4"), 1920, 1080, Path("a.wav"), ffmpeg.EncoderSettings()
    )
    text = " ".join(args)
    for expected in [
        "-c:v libx264",
        "-preset medium",
        "-crf 18",
        "-profile:v high",
        "-pix_fmt yuv420p",
        "-colorspace bt709",
        "-color_primaries bt709",
        "-color_trc bt709",
        "out_color_matrix=bt709",
        "-c:a aac",
        "-b:a 192k",
        "-ar 48000",
        "-ac 2",
        "-movflags +faststart",
        "-s 1920x1080",
        "-r 30",
    ]:
        assert expected in text
    assert args[-1] == "file:" + str(Path("v.mp4").absolute())


def test_frames_come_back_in_order_and_in_colour(tmp_path: Path) -> None:
    dest = tmp_path / "ordre.mp4"
    colour = np.array([200, 60, 30], dtype=np.uint8)
    writer = ffmpeg.open_encoder(dest, 64, 48, None, ffmpeg.EncoderSettings())
    for n in range(30):
        frame = gray_frame(64, 48, 8 * n)
        frame[:, 32:] = colour
        writer.write(frame)
    writer.close()
    times = [(n + 0.5) / 30 for n in (0, 1, 7, 15, 29)] + [10 / 30, 7 / 30]
    frames = ffmpeg.extract_frames(dest, times)
    for t, frame in zip(times, frames, strict=True):
        n = int(t * 30 + 1e-6)
        assert frame.shape == (48, 64, 3) and frame.dtype == np.uint8
        assert abs(int(np.median(frame[:, :24])) - 8 * n) <= 3, f"instant {t}: s'esperava la imatge {n}"
        right = np.median(frame[:, 40:].reshape(-1, 3), axis=0)
        assert np.all(np.abs(right - colour) <= 4), right


def test_stderr_flood_does_not_block_the_encoder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # At debug level x264 and ffmpeg write far more than a pipe buffer holds.
    monkeypatch.setattr(_video, "ENCODER_LOG_LEVEL", "debug")
    frame = gray_frame(1920, 1080, 90)

    def encode() -> None:
        writer = ffmpeg.open_encoder(tmp_path / "xerraire.mp4", 1920, 1080, None, FAST)
        for _ in range(90):
            writer.write(frame)
        writer.close()

    run_with_watchdog(encode, 120)
    assert ffmpeg.probe(tmp_path / "xerraire.mp4").has_video


def test_abort_stops_and_deletes_in_under_two_seconds(tmp_path: Path) -> None:
    dest = tmp_path / "cancel·lat.mp4"
    writer = ffmpeg.open_encoder(dest, 1920, 1080, None)
    frame = gray_frame(1920, 1080, 120)
    for _ in range(60):
        writer.write(frame)
    start = time.monotonic()
    writer.abort()
    assert time.monotonic() - start < 2.0
    assert not dest.exists()
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        writer.write(frame)
    assert caught.value.message_key == ffmpeg.ERROR_ABORTED
    writer.abort()  # A second abort is harmless.


def test_abort_from_another_thread_while_writing(tmp_path: Path) -> None:
    dest = tmp_path / "des d'un altre fil.mp4"
    writer = ffmpeg.open_encoder(dest, 1920, 1080, None)
    frame = gray_frame(1920, 1080, 30)
    stopped = threading.Event()

    def keep_writing() -> None:
        try:
            while True:
                writer.write(frame)
        except ffmpeg.FfmpegError as error:
            assert error.message_key == ffmpeg.ERROR_ABORTED
            stopped.set()

    thread = threading.Thread(target=keep_writing, daemon=True)
    thread.start()
    time.sleep(0.5)
    start = time.monotonic()
    writer.abort()
    assert stopped.wait(2.0)
    assert time.monotonic() - start < 2.0
    assert not dest.exists()


def test_wrong_frames_are_rejected(tmp_path: Path) -> None:
    writer = ffmpeg.open_encoder(tmp_path / "x.mp4", 64, 48, None, FAST)
    try:
        with pytest.raises(ValueError):
            writer.write(gray_frame(48, 64, 0))
        with pytest.raises(ValueError):
            writer.write(np.zeros((48, 64, 3), dtype=np.float32))  # pyright: ignore[reportArgumentType]
    finally:
        writer.abort()


def test_odd_sizes_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ffmpeg.open_encoder(tmp_path / "x.mp4", 641, 480, None)


def test_an_encoder_failure_is_an_ffmpeg_error_and_leaves_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "malament.mp4"
    writer = ffmpeg.open_encoder(dest, 64, 48, None, ffmpeg.EncoderSettings(preset="no_existeix"))
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        for _ in range(300):
            writer.write(gray_frame(64, 48, 0))
            time.sleep(0.001)
        writer.close()
    assert caught.value.message_key == ffmpeg.ERROR_ENCODE
    assert caught.value.detail
    assert not dest.exists()


def test_writing_to_a_missing_folder_is_a_write_error(tmp_path: Path) -> None:
    writer = ffmpeg.open_encoder(tmp_path / "no hi és" / "v.mp4", 64, 48, None, FAST)
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        for _ in range(300):
            writer.write(gray_frame(64, 48, 0))
            time.sleep(0.001)
        writer.close()
    assert caught.value.message_key == ffmpeg.ERROR_WRITE


def test_missing_audio_is_reported_before_starting(tmp_path: Path) -> None:
    with pytest.raises(ffmpeg.FfmpegError) as caught:
        ffmpeg.open_encoder(tmp_path / "v.mp4", 64, 48, tmp_path / "no.wav")
    assert caught.value.message_key == ffmpeg.ERROR_FILE_NOT_FOUND


@pytest.mark.lent
def test_ten_minutes_of_1080p_without_blocking(tmp_path: Path) -> None:
    """Criterion of B7: 10 minutes of 1080p frames through the pipe (ultrafast: the pipe is under test)."""
    fps = 30
    frames = [gray_frame(1920, 1080, level) for level in (40, 80, 120, 160)]
    for i, frame in enumerate(frames):
        frame[i * 200 : i * 200 + 200, :] = 220
    dest = tmp_path / "deu minuts.mp4"

    def encode() -> None:
        writer = ffmpeg.open_encoder(dest, 1920, 1080, None, FAST)
        for n in range(10 * 60 * fps):
            writer.write(frames[(n // fps) % len(frames)])
        writer.close()

    run_with_watchdog(encode, 25 * 60)
    info = ffmpeg.probe(dest)
    assert abs(info.duration_s - 600.0) <= 0.1
    last = ffmpeg.extract_frames(dest, [599.5])[0]
    assert last.shape == (1080, 1920, 3)
