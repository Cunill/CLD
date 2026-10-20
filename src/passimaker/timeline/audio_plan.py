"""Audio plan: songs one after another from the start, trimmed and with their fades (§1.7)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from passimaker.model import defaults
from passimaker.model.types import Song
from passimaker.timeline.types import AudioPlan, AudioSegment, Interval

SHORT_SONG_FADE_FRACTION = 0.4
"""§1.7: a song shorter than its two fades gets each fade reduced to 40 % of its length."""


def song_span(song: Song) -> tuple[float, float]:
    """(start, end) of the part of the file that is played, after the trim."""
    end = song.original_duration_s if song.trim_end_s is None else song.trim_end_s
    end = min(end, song.original_duration_s)
    start = max(0.0, song.trim_start_s)
    return start, max(start, end)


def music_duration(songs: Sequence[Song]) -> float:
    """Total length of the music: the sum of the songs, already trimmed."""
    return math.fsum(end - start for start, end in map(song_span, songs))


def build_audio_plan(songs: Sequence[Song], total_s: float, fps: int) -> AudioPlan:
    """Places the songs back to back from 0 and cuts the music at the end of the show.

    If the music is longer than the show (by more than half a frame), the segment that is cut
    loses its own fade-out and the final fade brings the volume to 0 exactly at `total_s`.
    """
    excess = music_duration(songs) - total_s
    final_fade = None
    if total_s > 0 and excess > 0.5 / fps:
        final_fade = Interval(max(0.0, total_s - defaults.MUSIC_FINAL_FADE_S), total_s)
    segments: list[AudioSegment] = []
    position = 0.0
    for song in songs:
        source_start, source_end = song_span(song)
        length = source_end - source_start
        video_start, video_end = position, position + length
        if video_end <= video_start:  # empty (or too short to place) songs are left out
            continue
        position = video_end
        if video_start >= total_s:
            break
        fade_in, fade_out = _song_fades(song, length)
        if video_end > total_s:
            video_end = total_s
            fade_in = min(fade_in, video_end - video_start)
            fade_out = 0.0 if final_fade is not None else min(fade_out, video_end - video_start - fade_in)
        segments.append(AudioSegment(song.id, video_start, video_end, source_start, fade_in, fade_out))
    return AudioPlan(tuple(segments), final_fade)


def _song_fades(song: Song, length: float) -> tuple[float, float]:
    """Fade lengths in seconds; disabled fades still get the inaudible anti-click fade."""
    micro = defaults.CUT_MICRO_FADE_S
    fade_in = max(micro, song.fade_in.seconds) if song.fade_in.enabled else micro
    fade_out = max(micro, song.fade_out.seconds) if song.fade_out.enabled else micro
    if fade_in + fade_out > length:
        limit = SHORT_SONG_FADE_FRACTION * length
        fade_in, fade_out = min(fade_in, limit), min(fade_out, limit)
    return fade_in, fade_out
