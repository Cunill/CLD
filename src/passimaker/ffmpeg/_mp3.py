"""MP3 conversion for the songs downloaded from YouTube (contract §8, block C04)."""

from __future__ import annotations

import threading
from pathlib import Path

from passimaker.common import CancelToken, ProgressCallback
from passimaker.ffmpeg._audio import DECODE_TIMEOUT_S, QUIET, ffprobe_streams
from passimaker.ffmpeg._locate import locate
from passimaker.ffmpeg._process import (
    StreamingProcess,
    classify,
    error_detail,
    media_url,
    os_path,
    remove_file,
)
from passimaker.ffmpeg.types import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    ERROR_FAILED,
    ERROR_NO_AUDIO,
    ERROR_WRITE,
    FfmpegError,
    Mp3Tags,
)

MIN_BITRATE_KBPS = 8
MAX_BITRATE_KBPS = 320
"""The constant bitrates that MP3 (MPEG-1/2 layer III) allows lie within this range."""

PARTIAL_SUFFIX = ".part"
"""The MP3 is written as `<name>.mp3.part` next to the destination and renamed at the end."""

CANCEL_POLL_S = 0.05
"""How often the watcher thread checks the cancel token (ffmpeg is killed well within 2 s)."""

ID3_VERSION = 3
"""ID3v2.3 (UTF-16 text): read by Windows Explorer and every player; v2.4 is not read by all of them."""


def partial_path(dest: Path) -> Path:
    return dest.with_name(dest.name + PARTIAL_SUFFIX)


def _tag_args(tags: Mp3Tags) -> list[str]:
    args: list[str] = []
    for key, value in (("title", tags.title), ("artist", tags.artist), ("comment", tags.comment)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    return args


def _parse_out_time_ms(line: str) -> int | None:
    """Milliseconds of output written, from a `-progress` line (`out_time_us=...`)."""
    key, _, value = line.partition("=")
    if key != "out_time_us":
        return None
    try:
        return max(0, int(value) // 1000)
    except ValueError:
        return None  # "N/A" before the first packet


def _watch(process: StreamingProcess, cancel: CancelToken, finished: threading.Event) -> None:
    """Kills ffmpeg as soon as the token is cancelled (the progress pipe may be quiet for a while)."""
    while not finished.wait(CANCEL_POLL_S):
        if cancel.cancelled:
            process.kill()
            return


def convert_to_mp3(
    source: Path,
    dest: Path,
    bitrate_kbps: int,
    tags: Mp3Tags,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> None:
    """Converts any audio file to MP3 (libmp3lame, constant `bitrate_kbps`, 48 kHz stereo, ID3 `tags`).

    Writes to a temporary file next to `dest` and renames it at the end: if it fails or is cancelled,
    `dest` is not created (an existing `dest` stays as it was). Progress is reported in milliseconds
    of audio. After a cancellation the function returns normally, so the caller checks its token.
    Errors: FfmpegError with the ERROR_* keys of this module.
    """
    if not MIN_BITRATE_KBPS <= bitrate_kbps <= MAX_BITRATE_KBPS:
        raise ValueError(f"bitrate_kbps ha de ser entre {MIN_BITRATE_KBPS} i {MAX_BITRATE_KBPS}")
    streams = ffprobe_streams(source)
    audio = streams.audio
    if audio is None:
        raise FfmpegError(ERROR_NO_AUDIO, str(source))
    if cancel is not None and cancel.cancelled:
        return
    total_ms = max(1, round(streams.duration_s * 1000))
    # A mono song plays at full level on both sides (ffmpeg's own upmix would lower it 3 dB).
    mono = str(audio.get("channels", "")) == "1"
    filters = [*(["pan=stereo|c0=c0|c1=c0"] if mono else []), f"aresample={AUDIO_SAMPLE_RATE}"]
    partial = partial_path(dest)
    args = [
        str(locate().ffmpeg),
        *QUIET,
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        media_url(source),
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-af",
        ",".join(filters),
        "-ac",
        str(AUDIO_CHANNELS),
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate_kbps}k",
        *_tag_args(tags),
        "-id3v2_version",
        str(ID3_VERSION),
        "-f",
        "mp3",
        "-y",
        media_url(partial),
    ]
    process = StreamingProcess(args, stdin=False, stdout=True)
    finished = threading.Event()
    watcher = None
    if cancel is not None:
        watcher = threading.Thread(
            target=_watch, args=(process, cancel, finished), name="ffmpeg-mp3-cancel", daemon=True
        )
        watcher.start()
    done = 0
    try:
        try:
            for raw in process.stdout:
                written = _parse_out_time_ms(raw.decode("ascii", errors="replace").strip())
                if written is not None and progress is not None and min(written, total_ms) > done:
                    done = min(written, total_ms)
                    progress(done, total_ms)
        except (OSError, ValueError):
            pass  # The pipe was closed by a cancellation: the exit code and the token tell.
        code = process.wait(DECODE_TIMEOUT_S)
    except BaseException:
        process.kill()
        remove_file(partial)
        raise
    finally:
        finished.set()
        if watcher is not None:
            watcher.join()
    if cancel is not None and cancel.cancelled:
        remove_file(partial)
        return
    if code != 0:
        stderr = process.stderr_text()
        remove_file(partial)
        raise FfmpegError(classify(stderr, ERROR_FAILED, writing=True), error_detail(stderr))
    try:
        Path(os_path(partial)).replace(os_path(dest))
    except OSError as error:
        remove_file(partial)
        raise FfmpegError(ERROR_WRITE, f"{dest}: {error}") from error
    if progress is not None:
        progress(total_ms, total_ms)
