"""Reading files: probe, decode_audio, measure_loudness and waveform."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from passimaker.ffmpeg._locate import locate
from passimaker.ffmpeg._process import (
    StreamingProcess,
    classify,
    error_detail,
    media_url,
    os_path,
    remove_file,
    require_file,
    run,
)
from passimaker.ffmpeg.types import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    ERROR_FAILED,
    ERROR_NO_AUDIO,
    ERROR_UNREADABLE,
    FfmpegError,
    Loudness,
    MediaInfo,
    PcmFile,
)

PROBE_TIMEOUT_S = 60.0
"""ffprobe on a local file answers in milliseconds; the margin is for slow network drives."""

DECODE_TIMEOUT_S = 600.0
"""Upper bound for decoding a whole song (a 2-hour file decodes in well under a minute)."""

PCM_FRAME_BYTES = AUDIO_CHANNELS * 4
"""Bytes per stereo float32 frame in a PcmFile."""

_READ_CHUNK = 1 << 20

# ffmpeg options shared by every run: no keyboard, no banner, no progress lines on stderr.
QUIET = ("-nostdin", "-hide_banner", "-nostats")


@dataclass(frozen=True, slots=True)
class Streams:
    """What ffprobe says about a file (the first audio stream and the first real video stream)."""

    duration_s: float
    audio: dict[str, Any] | None
    video: dict[str, Any] | None
    format_name: str

    @property
    def exact_container_duration(self) -> bool:
        """MP4/M4A/MOV store the real length (edit list); the AAC decoder adds the encoder padding."""
        return "mp4" in self.format_name.split(",") or "mov" in self.format_name.split(",")


def _number(value: object) -> float | None:
    try:
        number = float(str(value))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _is_cover(stream: dict[str, Any]) -> bool:
    """A picture attached to a song (album cover) is reported as a video stream."""
    disposition: dict[str, Any] = stream.get("disposition") or {}
    return bool(disposition.get("attached_pic"))


def ffprobe_streams(path: Path) -> Streams:
    require_file(path)
    args = [
        str(locate().ffprobe),
        "-v",
        "error",
        "-hide_banner",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        media_url(path),
    ]
    result = run(args, PROBE_TIMEOUT_S)
    if result.returncode != 0:
        raise FfmpegError(classify(result.stderr, ERROR_UNREADABLE), error_detail(result.stderr))
    try:
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error:
        raise FfmpegError(ERROR_UNREADABLE, f"{path}: {error}") from error
    streams: list[dict[str, Any]] = [s for s in data.get("streams", []) if isinstance(s, dict)]
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next((s for s in streams if s.get("codec_type") == "video" and not _is_cover(s)), None)
    container: dict[str, Any] = data.get("format") or {}
    duration = _number(container.get("duration"))
    if duration is None:
        durations = [d for s in streams if (d := _number(s.get("duration"))) is not None]
        duration = max(durations, default=0.0)
    if audio is None and video is None and not streams:
        raise FfmpegError(ERROR_UNREADABLE, f"{path}: sense pistes")
    return Streams(max(0.0, duration), audio, video, str(container.get("format_name", "")))


def _int(stream: dict[str, Any] | None, key: str) -> int | None:
    if stream is None:
        return None
    value = _number(stream.get(key))
    return round(value) if value is not None and value > 0 else None


def _decoded_frames(path: Path, sample_rate: int) -> int:
    """Exact length in samples, by decoding the first audio stream (mono 16-bit, native rate)."""
    args = [
        str(locate().ffmpeg),
        *QUIET,
        "-loglevel",
        "error",
        "-i",
        media_url(path),
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = StreamingProcess(args, stdin=False, stdout=True)
    total = 0
    try:
        while chunk := process.stdout.read(_READ_CHUNK):
            total += len(chunk)
    finally:
        code = process.wait(DECODE_TIMEOUT_S)
    if code != 0:
        stderr = process.stderr_text()
        raise FfmpegError(classify(stderr, ERROR_UNREADABLE), error_detail(stderr))
    return total // 2


def probe(path: Path) -> MediaInfo:
    """Duration, audio and video characteristics.

    The duration of an audio-only file is exactly the length that decode_audio produces. For
    compressed formats other than MP4/M4A it comes from decoding the file, because the container
    value can be tens of milliseconds off (MP3 counts the encoder delay and padding).
    """
    streams = ffprobe_streams(path)
    audio, video = streams.audio, streams.video
    sample_rate = _int(audio, "sample_rate")
    duration = streams.duration_s
    if audio is not None and video is None and sample_rate is not None:
        codec = str(audio.get("codec_name", ""))
        if not codec.startswith("pcm_") and not streams.exact_container_duration:
            duration = _decoded_frames(path, sample_rate) / sample_rate
    return MediaInfo(
        duration_s=duration,
        has_audio=audio is not None,
        sample_rate=sample_rate,
        channels=_int(audio, "channels"),
        has_video=video is not None,
        width=_int(video, "width"),
        height=_int(video, "height"),
    )


def _audio_stream(path: Path) -> dict[str, Any]:
    audio = ffprobe_streams(path).audio
    if audio is None:
        raise FfmpegError(ERROR_NO_AUDIO, str(path))
    return audio


def _to_stereo_filter(audio: dict[str, Any]) -> list[str]:
    """A mono song plays at full level on both sides (ffmpeg's own upmix would lower it 3 dB)."""
    return ["pan=stereo|c0=c0|c1=c0"] if _int(audio, "channels") == 1 else []


def decode_audio(path: Path, dest: Path, start_s: float = 0.0, end_s: float | None = None) -> PcmFile:
    """Decodes [start_s, end_s) of the first audio stream to raw float32 stereo at 48 kHz.

    The cut is sample-exact (it is applied after resampling, counting samples). A range outside the
    file gives fewer frames, or none. If decoding fails the partial dest is deleted.
    """
    streams = ffprobe_streams(path)
    audio = streams.audio
    if audio is None:
        raise FfmpegError(ERROR_NO_AUDIO, str(path))
    if streams.exact_container_duration and streams.duration_s > 0:
        # Drop the AAC padding after the real end, as probe() reports it.
        end_s = streams.duration_s if end_s is None else min(end_s, streams.duration_s)
    start = max(0, round(max(0.0, start_s) * AUDIO_SAMPLE_RATE))
    filters = [*_to_stereo_filter(audio), f"aresample={AUDIO_SAMPLE_RATE}"]
    trim = f"atrim=start_sample={start}"
    if end_s is not None:
        end = max(start, round(end_s * AUDIO_SAMPLE_RATE))
        trim += f":end_sample={end}"
    filters.append(trim)
    args = [
        str(locate().ffmpeg),
        *QUIET,
        "-loglevel",
        "error",
        "-i",
        media_url(path),
        "-map",
        "0:a:0",
        "-af",
        ",".join(filters),
        "-ac",
        str(AUDIO_CHANNELS),
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-c:a",
        "pcm_f32le",
        "-f",
        "f32le",
        "-y",
        media_url(dest),
    ]
    result = run(args, DECODE_TIMEOUT_S)
    if result.returncode != 0:
        remove_file(dest)
        raise FfmpegError(
            classify(result.stderr, ERROR_UNREADABLE, writing=True), error_detail(result.stderr)
        )
    size = Path(os_path(dest)).stat().st_size
    return PcmFile(dest, size // PCM_FRAME_BYTES)


_SUMMARY = re.compile(r"Summary:(?P<body>.*)", re.DOTALL)
_INTEGRATED = re.compile(r"\bI:\s*(?P<value>-?(?:inf|[0-9.]+))\s*LUFS")
_PEAK = re.compile(r"\bPeak:\s*(?P<value>-?(?:inf|[0-9.]+))\s*dBFS")


def parse_ebur128_summary(stderr: str) -> Loudness:
    """Reads the summary that the ebur128 filter prints when it ends."""
    summary = _SUMMARY.search(stderr)
    body = summary.group("body") if summary else ""
    integrated = _INTEGRATED.search(body)
    peak = _PEAK.search(body)
    if integrated is None or peak is None:
        raise FfmpegError(ERROR_FAILED, "ebur128: " + error_detail(stderr))
    return Loudness(float(integrated.group("value")), float(peak.group("value")))


def measure_loudness(path: Path) -> Loudness:
    """EBU R128 integrated loudness and true peak of the first audio stream, as it will be played
    (mono counted on both sides)."""
    audio = _audio_stream(path)
    filters = [*_to_stereo_filter(audio), "ebur128=peak=true:framelog=quiet"]
    args = [
        str(locate().ffmpeg),
        *QUIET,
        "-loglevel",
        "info",
        "-i",
        media_url(path),
        "-map",
        "0:a:0",
        "-af",
        ",".join(filters),
        "-f",
        "null",
        "-",
    ]
    result = run(args, DECODE_TIMEOUT_S)
    if result.returncode != 0:
        raise FfmpegError(classify(result.stderr, ERROR_UNREADABLE), error_detail(result.stderr))
    return parse_ebur128_summary(result.stderr)


WAVEFORM_BLOCKS_PER_POINT = 4
"""Resolution of the first reduction pass, relative to the requested number of points."""


def waveform(path: Path, points: int) -> NDArray[np.float32]:
    """Peak amplitude (0-1) per bucket, `points` buckets of equal length over the whole file.

    The file is decoded at its own sample rate and read in chunks: the memory used does not depend
    on the song length.
    """
    if points < 1:
        raise ValueError("points ha de ser 1 o més")
    streams = ffprobe_streams(path)
    audio = streams.audio
    if audio is None:
        raise FfmpegError(ERROR_NO_AUDIO, str(path))
    rate = _int(audio, "sample_rate") or AUDIO_SAMPLE_RATE
    channels = _int(audio, "channels") or 1
    estimated = max(1, round(streams.duration_s * rate))
    block = max(1, min(4096, estimated // (points * WAVEFORM_BLOCKS_PER_POINT)))
    args = [
        str(locate().ffmpeg),
        *QUIET,
        "-loglevel",
        "error",
        "-i",
        media_url(path),
        "-map",
        "0:a:0",
        "-c:a",
        "pcm_f32le",
        "-f",
        "f32le",
        "pipe:1",
    ]
    frame_bytes = 4 * channels
    process = StreamingProcess(args, stdin=False, stdout=True)
    block_peaks: list[NDArray[np.float32]] = []
    pending = np.zeros(0, dtype=np.float32)
    leftover = b""
    try:
        while chunk := process.stdout.read(_READ_CHUNK):
            data = leftover + chunk
            usable = len(data) - len(data) % frame_bytes
            leftover = data[usable:]
            samples = np.frombuffer(data[:usable], dtype="<f4").reshape(-1, channels)
            mono_peak = np.abs(samples).max(axis=1) if samples.size else np.zeros(0, np.float32)
            pending = np.concatenate([pending, mono_peak.astype(np.float32)])
            whole = len(pending) - len(pending) % block
            if whole:
                block_peaks.append(pending[:whole].reshape(-1, block).max(axis=1))
                pending = pending[whole:]
    finally:
        code = process.wait(DECODE_TIMEOUT_S)
    if code != 0:
        stderr = process.stderr_text()
        raise FfmpegError(classify(stderr, ERROR_UNREADABLE), error_detail(stderr))
    if len(pending):
        block_peaks.append(np.array([pending.max()], dtype=np.float32))
    peaks = np.concatenate(block_peaks) if block_peaks else np.zeros(0, dtype=np.float32)
    result = np.zeros(points, dtype=np.float32)
    if len(peaks):
        edges = np.linspace(0, len(peaks), points + 1)
        lo = np.floor(edges[:-1]).astype(np.int64)
        hi = np.maximum(np.ceil(edges[1:]).astype(np.int64), lo + 1)
        hi = np.minimum(hi, len(peaks))
        for i in range(points):
            if lo[i] < hi[i]:
                result[i] = peaks[lo[i] : hi[i]].max()
    return np.clip(result, 0.0, 1.0)
