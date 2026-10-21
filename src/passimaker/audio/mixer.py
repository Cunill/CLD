"""The mix: songs placed by the audio plan, with fades, gains, limiter, master volume and final fade.

Every position is an integer frame at 48 kHz, computed once from the plan. A block is mixed from
the frames it needs and nothing else (the limiter looks only at a fixed neighbourhood), so
`read` can serve any instant in any order, and `render_wav` produces exactly the same samples
block after block without ever holding the whole mix in memory.

Signal chain: song × (normalisation · song volume) × fades → sum → limiter → × master volume ×
final fade. The master volume and the final fade only lower the level, so they go after the
limiter: the volume is exact and the peaks stay below the ceiling.
"""

from __future__ import annotations

import contextlib
import wave
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from passimaker.audio import limiter
from passimaker.audio.cache import DecodedSong
from passimaker.audio.curves import fade_out_envelope, segment_envelope
from passimaker.audio.params import (
    CHANNELS,
    LIMITER_CEILING,
    LIMITER_HOLD_S,
    LIMITER_LOOKAHEAD_S,
    RENDER_BLOCK_FRAMES,
    SAMPLE_RATE,
)
from passimaker.common import AudioBlock, CancelToken, PassiMakerError, ProgressCallback
from passimaker.timeline import AudioPlan

INT16_SCALE = 32767


def to_frame(t_s: float) -> int:
    return round(t_s * SAMPLE_RATE)


@dataclass(frozen=True, slots=True)
class Track:
    """A decoded song and the linear gain applied to it before the sum (normalisation × volume)."""

    song: DecodedSong
    gain: float


@dataclass(frozen=True, slots=True)
class Placement:
    """One segment of the plan in frames: plays song frames from `source` on over [start, end)."""

    track: Track
    start: int
    end: int
    source: int
    fade_in: int
    fade_out: int


def place(plan: AudioPlan, tracks: Mapping[str, Track]) -> tuple[Placement, ...]:
    """Segments of the plan in frames; songs without a track (unreadable) are left out (silence)."""
    placements: list[Placement] = []
    for segment in plan.segments:
        track = tracks.get(segment.song_id)
        start, end = to_frame(segment.video_start), to_frame(segment.video_end)
        if track is None or end <= start:
            continue
        length = end - start
        placements.append(
            Placement(
                track=track,
                start=start,
                end=end,
                source=to_frame(segment.source_start),
                fade_in=min(length, to_frame(segment.fade_in_s)),
                fade_out=min(length, to_frame(segment.fade_out_s)),
            )
        )
    return tuple(placements)


@dataclass(frozen=True)
class MixedAudioSource:
    """Implements passimaker.audio.AudioSource. Immutable and thread-safe."""

    placements: tuple[Placement, ...]
    total_frames: int
    """Length of the mix; also the length of the WAV (the video's length in samples)."""
    master_volume: float = 1.0
    final_fade: tuple[int, int] | None = None
    """[start, end) frames of the fade applied when the music is longer than the show."""
    failures: Mapping[str, PassiMakerError] = field(default_factory=dict[str, PassiMakerError])
    """Songs that could not be read (song id → error); their place in the plan stays silent."""
    measured_gains_db: Mapping[str, float] = field(default_factory=dict[str, float])
    """Normalisation gains measured by prepare() for songs whose loudness_gain_db was None."""
    lookahead: int = to_frame(LIMITER_LOOKAHEAD_S)
    hold: int = to_frame(LIMITER_HOLD_S)

    @property
    def duration_s(self) -> float:
        return self.total_frames / SAMPLE_RATE

    def read(self, t_s: float, frames: int) -> AudioBlock:
        """`frames` frames of the mix from t_s (rounded to the nearest sample); zeros outside it."""
        return self.mix(to_frame(t_s), max(0, frames))

    def mix(self, first: int, count: int) -> AudioBlock:
        """Frames [first, first + count) of the mix."""
        out = np.zeros((count, CHANNELS), dtype=np.float32)
        lo, hi = max(0, first), min(self.total_frames, first + count)
        if hi <= lo or self.master_volume <= 0:
            return out
        before, after = limiter.context(self.lookahead, self.hold)
        summed = self._sum(lo - before, hi + after)
        if np.abs(summed).max(initial=0.0) > LIMITER_CEILING:
            block = limiter.limit(summed, self.lookahead, self.hold, LIMITER_CEILING)
        else:  # the limiter would leave every frame as it is
            block = summed[before : before + hi - lo]
        gain = np.full(hi - lo, self.master_volume, dtype=np.float64)
        if self.final_fade is not None:
            gain *= fade_out_envelope(lo, hi - lo, *self.final_fade)
        out[lo - first : hi - first] = block * gain[:, None].astype(np.float32)
        return out

    def _sum(self, first: int, end: int) -> AudioBlock:
        """Songs with their gains and fades over [first, end), before the limiter."""
        summed = np.zeros((end - first, CHANNELS), dtype=np.float32)
        for p in self.placements:
            lo, hi = max(first, p.start), min(end, p.end)
            if hi <= lo or p.track.gain <= 0:
                continue
            samples = p.track.song.read(lo - p.start + p.source, hi - lo)
            gain = p.track.gain * segment_envelope(lo, hi - lo, p.start, p.end, p.fade_in, p.fade_out)
            summed[lo - first : hi - first] += samples * gain[:, None].astype(np.float32)
        return summed

    def render_wav(
        self, dest: Path, progress: ProgressCallback | None = None, cancel: CancelToken | None = None
    ) -> None:
        """Writes the whole mix as 16-bit stereo PCM WAV at 48 kHz, block by block.

        Progress is reported in frames. If cancelled (or on any error) the partial file is deleted;
        after a cancellation the method returns normally, so the caller checks its token. Writing
        errors are raised as OSError (errno.ENOSPC when the disk is full).
        """
        total = self.total_frames
        done = 0
        completed = False
        try:
            with wave.open(str(dest), "wb") as writer:
                writer.setnchannels(CHANNELS)
                writer.setsampwidth(2)
                writer.setframerate(SAMPLE_RATE)
                while done < total:
                    if cancel is not None and cancel.cancelled:
                        break
                    count = min(RENDER_BLOCK_FRAMES, total - done)
                    block = self.mix(done, count)
                    pcm = np.round(np.clip(block, -1.0, 1.0) * INT16_SCALE).astype("<i2")
                    writer.writeframesraw(pcm.tobytes())
                    done += count
                    if progress is not None:
                        progress(done, total)
            completed = done >= total  # only once the header has been written on closing
        finally:
            if not completed and dest.is_file():  # never a device such as /dev/null
                with contextlib.suppress(OSError):
                    dest.unlink()
        if progress is not None and total == 0:
            progress(0, 0)
