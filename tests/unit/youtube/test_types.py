"""C01: errors, message keys and defaults of the YouTube music module (contract §15)."""

from __future__ import annotations

from passimaker import ffmpeg, youtube
from passimaker.common import PassiMakerError
from passimaker.i18n import MESSAGES, message
from passimaker.model import defaults
from passimaker.youtube import types


def test_every_error_key_has_a_catalan_message() -> None:
    keys = {v for name, v in vars(types).items() if name.startswith("ERROR_") and isinstance(v, str)}
    assert len(keys) == 7
    for key in keys:
        assert key.startswith("youtube.") and key in MESSAGES
        assert message(key) != key


def test_errors_carry_their_key_and_derive_from_the_base_error() -> None:
    errors = [
        (youtube.YoutubeOfflineError(), youtube.ERROR_OFFLINE),
        (youtube.YoutubeUnavailableError(), youtube.ERROR_UNAVAILABLE),
        (youtube.YoutubeUnavailableError(youtube.ERROR_LIVE), youtube.ERROR_LIVE),
        (youtube.YoutubeBrokenError("ERROR: Sign in to confirm"), youtube.ERROR_BROKEN),
        (youtube.YoutubeTooLongError(), youtube.ERROR_TOO_LONG),
        (youtube.YoutubeConsentError(), youtube.ERROR_CONSENT),
    ]
    for error, key in errors:
        assert isinstance(error, youtube.YoutubeError) and isinstance(error, PassiMakerError)
        assert error.message_key == key


def test_the_too_long_message_matches_the_default() -> None:
    assert defaults.YOUTUBE_MAX_DURATION_S == 20 * 60
    assert "20 minuts" in message(youtube.ERROR_TOO_LONG)


def test_defaults_of_the_specification() -> None:
    assert defaults.YOUTUBE_RESULTS_PER_PAGE == 10
    assert defaults.YOUTUBE_MP3_BITRATE_KBPS == 192
    assert defaults.YOUTUBE_SIMULTANEOUS_DOWNLOADS == 2
    assert ffmpeg.AUDIO_SAMPLE_RATE == 48000  # the MP3s are 48 kHz like the mixer


def test_search_result_has_the_fields_of_the_contract() -> None:
    result = youtube.SearchResult(
        video_id="dQw4w9WgXcQ",
        title="Títol",
        channel="Canal",
        duration_s=None,
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
        is_live=False,
        url=youtube.watch_url("dQw4w9WgXcQ"),
    )
    assert youtube.parse_link(result.url) == result.video_id
