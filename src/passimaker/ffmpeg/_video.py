"""Writing video through a pipe (open_encoder) and reading frames back (extract_frames)."""

from __future__ import annotations

import contextlib
import math
import threading
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from passimaker.common import RGBImage
from passimaker.ffmpeg._audio import QUIET, ffprobe_streams
from passimaker.ffmpeg._locate import locate
from passimaker.ffmpeg._process import (
    StreamingProcess,
    classify,
    error_detail,
    media_url,
    remove_file,
    require_file,
    run,
)
from passimaker.ffmpeg.types import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    DEFAULT_ENCODER_SETTINGS,
    ERROR_ABORTED,
    ERROR_ENCODE,
    ERROR_UNREADABLE,
    EncoderSettings,
    FfmpegError,
)

ENCODER_LOG_LEVEL = "error"
"""ffmpeg's log level while encoding (its output is drained in parallel whatever the volume)."""

CLOSE_TIMEOUT_S = 600.0
"""Time ffmpeg may take to flush the encoder and write the index after the last frame."""

FRAME_TIMEOUT_S = 60.0

# Colour: frames are sRGB; the video is BT.709 limited range (ESPECIFICACIO §1.9), tagged as such.
# setparams tags the frames too: since FFmpeg 7.1 the encoder takes the colour tags from the frames
# and ignores -color_primaries / -color_trc when a filter left them unspecified.
_COLOUR_FILTER = (
    "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,"
    "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
)
_COLOUR_TAGS = (
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
)


def encoder_args(
    ffmpeg: Path, dest: Path, width: int, height: int, audio_wav: Path | None, settings: EncoderSettings
) -> list[str]:
    """Command line of the encoder: raw RGB frames on stdin, optional WAV, MP4 out."""
    args = [str(ffmpeg), *QUIET, "-loglevel", ENCODER_LOG_LEVEL, "-y"]
    args += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(settings.fps)]
    args += ["-i", "pipe:0"]
    if audio_wav is not None:
        args += ["-i", media_url(audio_wav)]
    args += ["-map", "0:v:0"]
    if audio_wav is not None:
        args += ["-map", "1:a:0"]
    args += ["-vf", _COLOUR_FILTER, "-c:v", "libx264", "-preset", settings.preset, "-crf", str(settings.crf)]
    args += ["-profile:v", settings.profile, "-pix_fmt", "yuv420p", *_COLOUR_TAGS, "-r", str(settings.fps)]
    if audio_wav is not None:
        args += ["-c:a", "aac", "-b:a", settings.audio_bitrate]
        args += ["-ar", str(AUDIO_SAMPLE_RATE), "-ac", str(AUDIO_CHANNELS)]
    args += ["-movflags", "+faststart", "-f", "mp4", media_url(dest)]
    return args


class FfmpegVideoWriter:
    """VideoWriter implementation. write() and close() run on one thread; abort() may come from any."""

    def __init__(self, dest: Path, width: int, height: int, args: Sequence[str]) -> None:
        self.dest = dest
        self.width = width
        self.height = height
        self.frames_written = 0
        self._lock = threading.Lock()
        self._finished = False
        self._aborted = False
        self._process = StreamingProcess(args, stdin=True, stdout=False)

    def write(self, frame: RGBImage) -> None:
        if self._aborted:
            raise FfmpegError(ERROR_ABORTED, str(self.dest))
        if self._finished:
            raise RuntimeError("VideoWriter ja tancat")
        if frame.shape != (self.height, self.width, 3) or frame.dtype != np.uint8:
            raise ValueError(
                f"s'esperava una imatge {self.height}×{self.width}×3 uint8; "
                f"s'ha rebut {frame.shape} {frame.dtype}"
            )
        data = np.ascontiguousarray(frame)
        try:
            self._process.stdin.write(memoryview(data).cast("B"))
        except (BrokenPipeError, OSError, ValueError) as error:
            if self._aborted:
                raise FfmpegError(ERROR_ABORTED, str(self.dest)) from error
            self._fail(error)
        self.frames_written += 1

    def close(self) -> None:
        if self._aborted:
            raise FfmpegError(ERROR_ABORTED, str(self.dest))
        if self._finished:
            return
        self._finished = True
        with contextlib.suppress(OSError, ValueError):  # the exit code below explains it
            self._process.stdin.flush()
        code = self._process.wait(CLOSE_TIMEOUT_S)
        if code != 0:
            self._fail(None)

    def abort(self) -> None:
        with self._lock:
            if self._aborted:
                return
            self._aborted = True
            self._finished = True
        self._process.kill()
        remove_file(self.dest)

    def _fail(self, cause: BaseException | None) -> None:
        """ffmpeg stopped: collect its message, delete the partial file and raise."""
        self._finished = True
        try:
            self._process.wait(10.0)
        except FfmpegError:
            self._process.kill()
        stderr = self._process.stderr_text()
        remove_file(self.dest)
        key = classify(stderr, ERROR_ENCODE, writing=True)
        raise FfmpegError(key, error_detail(stderr) or str(cause or "")) from cause


def open_encoder(
    dest: Path,
    width: int,
    height: int,
    audio_wav: Path | None,
    settings: EncoderSettings = DEFAULT_ENCODER_SETTINGS,
) -> FfmpegVideoWriter:
    """Starts an H.264/AAC MP4 encoder fed with RGB frames (contract §8).

    Frame n is shown at n / fps. The WAV (if any) should last as long as the video. The output goes
    straight to dest (export writes to a provisional name and renames it, ESPECIFICACIO §1.9).
    """
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError(f"mida de vídeo no vàlida (cal parell i positiu): {width}×{height}")
    if audio_wav is not None:
        require_file(audio_wav)
    args = encoder_args(locate().ffmpeg, dest, width, height, audio_wav, settings)
    return FfmpegVideoWriter(dest, width, height, args)


def _frame_rate(stream: dict[str, object]) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        text = str(stream.get(key, ""))
        num, _, den = text.partition("/")
        try:
            rate = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            continue
        if rate > 0 and math.isfinite(rate):
            return rate
    return float(DEFAULT_ENCODER_SETTINGS.fps)


def extract_frames(video: Path, times_s: Sequence[float]) -> list[RGBImage]:
    """The frame shown at each instant (frame n covers [n/fps, (n+1)/fps)), as RGB (for tests).

    The colour conversion follows the tags of the file, so a video from open_encoder comes back as
    the RGB that went in (minus compression).
    """
    streams = ffprobe_streams(video)
    stream = streams.video
    if stream is None:
        raise FfmpegError(ERROR_UNREADABLE, f"{video}: sense vídeo")
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    rate = _frame_rate(stream)
    ffmpeg = str(locate().ffmpeg)
    cache: dict[int, RGBImage] = {}
    frames: list[RGBImage] = []
    for t in times_s:
        index = max(0, math.floor(t * rate + 1e-6))
        if index not in cache:
            cache[index] = _frame_at_index(ffmpeg, video, index, rate, width, height)
        frames.append(cache[index].copy())
    return frames


def _frame_at_index(ffmpeg: str, video: Path, index: int, rate: float, width: int, height: int) -> RGBImage:
    # Seek a quarter of a frame before frame `index`: the previous frame is dropped, this one is first.
    seek = max(0.0, (index - 0.25) / rate)
    args = [ffmpeg, *QUIET, "-loglevel", "error", "-ss", f"{seek:.6f}", "-i", media_url(video)]
    args += ["-map", "0:v:0", "-frames:v", "1", "-vf", "scale=flags=accurate_rnd+full_chroma_int"]
    args += ["-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    result = run(args, FRAME_TIMEOUT_S)
    size = width * height * 3
    if result.returncode != 0 or len(result.stdout) < size:
        detail = error_detail(result.stderr) or f"{video}: no hi ha la imatge {index}"
        raise FfmpegError(classify(result.stderr, ERROR_UNREADABLE), detail)
    return np.frombuffer(result.stdout[:size], dtype=np.uint8).reshape(height, width, 3).copy()
