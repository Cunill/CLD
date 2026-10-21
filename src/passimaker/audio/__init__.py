"""M9 · Audio engine: sequential mix with trims, fades, volumes and normalisation (block B8).

prepare() decodes each song once into a cache folder (through passimaker.ffmpeg), measures its
loudness and returns a MixedAudioSource, which mixes any block on demand: small blocks for the
preview (`read`) and the whole show as a WAV for the export (`render_wav`). The mix is never held
in memory as a whole. prepare() can take seconds (decoding): never call it on the UI thread.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

from passimaker.audio.cache import DecodedSong, decoded_song, song_loudness
from passimaker.audio.mixer import MixedAudioSource, Track, place, to_frame
from passimaker.audio.params import (
    CHANNELS,
    MAX_NORMALIZE_GAIN_DB,
    SAMPLE_RATE,
    SILENCE_LUFS,
)
from passimaker.common import AudioBlock, CancelToken, PassiMakerError, ProgressCallback
from passimaker.ffmpeg import ERROR_DISK_FULL, ERROR_NOT_FOUND, ERROR_WRITE, FfmpegError
from passimaker.model import defaults
from passimaker.model.types import Project, Song
from passimaker.timeline import AudioPlan, compute_timeline

__all__ = [
    "CHANNELS",
    "SAMPLE_RATE",
    "AudioSource",
    "DecodedSong",
    "MixedAudioSource",
    "Track",
    "normalisation_gain_db",
    "prepare",
]

ENVIRONMENT_ERRORS = frozenset({ERROR_NOT_FOUND, ERROR_DISK_FULL, ERROR_WRITE})
"""Failures that are not the song's fault (no FFmpeg, cache disk full or not writable): prepare()
raises them instead of leaving the song silent."""


class AudioSource(Protocol):
    @property
    def duration_s(self) -> float: ...

    def read(self, t_s: float, frames: int) -> AudioBlock:
        """Mixed audio from t_s; zero-padded past the end. Fast enough for real time."""
        ...

    def render_wav(
        self, dest: Path, progress: ProgressCallback | None = None, cancel: CancelToken | None = None
    ) -> None:
        """Writes the whole mix (duration of the show) as 16-bit PCM WAV, block by block."""
        ...


def normalisation_gain_db(integrated_lufs: float) -> float:
    """Gain that brings a song to the loudness target (−16 LUFS); 0 dB for silence."""
    if not math.isfinite(integrated_lufs) or integrated_lufs <= SILENCE_LUFS:
        return 0.0
    return min(MAX_NORMALIZE_GAIN_DB, defaults.LOUDNESS_TARGET_LUFS - integrated_lufs)


def prepare(project: Project, plan: AudioPlan, cache_dir: Path) -> MixedAudioSource:
    """Decodes each song once into cache_dir (via passimaker.ffmpeg) and returns the mixer.

    The length of the mix is the length of the video (compute_timeline(project).total_frames at
    its fps), so the WAV and the video always match. A song that cannot be read (missing, corrupt,
    protected) is reported in `failures` and its place stays silent; a missing FFmpeg or a cache
    folder that cannot be written raises FfmpegError.

    With normalisation on, songs whose `loudness_gain_db` is None are measured once (cached);
    the gains measured are in `measured_gains_db`, so the controller can store them.
    """
    timeline = compute_timeline(project)
    total_frames = round(timeline.total_frames * SAMPLE_RATE / timeline.fps)
    songs = {song.id: song for song in project.music.songs}
    needed = dict.fromkeys(s.song_id for s in plan.segments if s.song_id in songs)
    if needed:
        cache_dir.mkdir(parents=True, exist_ok=True)
    tracks: dict[str, Track] = {}
    failures: dict[str, PassiMakerError] = {}
    measured: dict[str, float] = {}
    for song_id in needed:
        song = songs[song_id]
        try:
            decoded = decoded_song(song.path, cache_dir)
            gain_db = _gain_db(song, project.music.normalize, cache_dir, measured)
        except FfmpegError as error:
            if error.message_key in ENVIRONMENT_ERRORS:
                raise
            failures[song_id] = error
            continue
        tracks[song_id] = Track(decoded, 10.0 ** (gain_db / 20.0) * max(0.0, song.volume))
    final_fade = plan.final_fade
    return MixedAudioSource(
        placements=place(plan, tracks),
        total_frames=total_frames,
        master_volume=max(0.0, project.music.master_volume),
        final_fade=None if final_fade is None else (to_frame(final_fade.start), to_frame(final_fade.end)),
        failures=failures,
        measured_gains_db=measured,
    )


def _gain_db(song: Song, normalize: bool, cache_dir: Path, measured: dict[str, float]) -> float:
    if not normalize:
        return 0.0
    if song.loudness_gain_db is not None:
        return song.loudness_gain_db
    gain = normalisation_gain_db(song_loudness(song.path, cache_dir).integrated_lufs)
    measured[song.id] = gain
    return gain
