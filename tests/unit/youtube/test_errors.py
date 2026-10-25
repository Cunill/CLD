"""C03: yt-dlp's and the network's exceptions become this module's errors (ESPECIFICACIO §1.7 bis, "Errors").

Built with yt-dlp's own exception classes and the messages it gives for each case, wrapped the way
yt-dlp wraps them (DownloadError → ExtractorError → TransportError → socket error).
"""

from __future__ import annotations

import socket
import urllib.error
from concurrent.futures import CancelledError

import pytest
from yt_dlp.networking.exceptions import HTTPError, ProxyError, TransportError
from yt_dlp.utils import DownloadError, ExtractorError

from passimaker import youtube
from passimaker.youtube.errors import call, translate

ID = "dQw4w9WgXcQ"


def _wrapped(inner: BaseException) -> DownloadError:
    """What YoutubeDL.extract_info raises: report_error("ERROR: …", exc_info of the cause)."""
    try:
        raise inner
    except BaseException as error:
        assert error.__traceback__ is not None
        return DownloadError(f"ERROR: {inner}", (type(error), error, error.__traceback__))


def _extractor(message: str, cause: Exception | None = None) -> DownloadError:
    try:
        if cause is not None:
            raise cause
        raise ExtractorError(message, expected=True, video_id=ID)
    except ExtractorError as error:
        return _wrapped(error)
    except Exception as error:
        return _wrapped(ExtractorError(message, cause=error, video_id=ID))


def _key(error: BaseException) -> str:
    result = translate(error)
    assert isinstance(result, youtube.YoutubeError)
    return result.message_key


@pytest.mark.parametrize(
    "message",
    [
        "Private video. Sign in if you've been granted access to this video",
        "Video unavailable",
        "Video unavailable. This video is no longer available because the YouTube account associated "
        "with this video has been terminated.",
        "Video unavailable. This video has been removed by the uploader",
        "Sign in to confirm your age. This video may be inappropriate for some users.",
        "The uploader has not made this video available in your country",
        "Video unavailable. The uploader has not made this video available in your country",
        "Join this channel to get access to members-only content like this video, and other exclusive perks.",
        "This video contains content from SME, who has blocked it on copyright grounds",
    ],
)
def test_private_deleted_or_restricted(message: str) -> None:
    assert _key(_extractor(message)) == youtube.ERROR_UNAVAILABLE


@pytest.mark.parametrize(
    "message",
    ["This live event will begin in 3 hours.", "Premieres in 2 days", "This live event has ended."],
)
def test_live_streams(message: str) -> None:
    assert _key(_extractor(message)) == youtube.ERROR_LIVE


@pytest.mark.parametrize(
    "cause",
    [
        socket.gaierror(-3, "Temporary failure in name resolution"),
        socket.gaierror(11001, "getaddrinfo failed"),
        ConnectionRefusedError(111, "Connection refused"),
        TimeoutError("timed out"),
        OSError(101, "Network is unreachable"),
        urllib.error.URLError(OSError(113, "No route to host")),
    ],
)
def test_no_connection(cause: Exception) -> None:
    try:
        raise cause
    except Exception as error:
        try:
            raise TransportError(cause=error) from error
        except TransportError as transport:
            wrapped = _extractor("Unable to download API page", transport)
    assert _key(wrapped) == youtube.ERROR_OFFLINE
    assert _key(cause) == youtube.ERROR_OFFLINE  # also unwrapped (the thumbnails, with urllib)


def test_no_connection_through_a_proxy() -> None:
    assert _key(_wrapped(ProxyError("Unable to connect to proxy"))) == youtube.ERROR_OFFLINE


def test_windows_socket_errors_are_no_connection() -> None:
    error = OSError(0, "A connection attempt failed")
    error.winerror = 10060  # type: ignore[attr-defined]  # WSAETIMEDOUT
    assert _key(error) == youtube.ERROR_OFFLINE


@pytest.mark.parametrize(
    "message",
    [
        "Requested format is not available. Use --list-formats for a list of available formats",
        "Unable to extract yt initial data",
        "Signature extraction failed: Some formats may be missing",
        "n challenge solving failed: Some formats may be missing.",
    ],
)
def test_youtube_changed(message: str) -> None:
    error = translate(_extractor(message))
    assert isinstance(error, youtube.YoutubeBrokenError)
    assert message[:30] in error.detail  # the detail goes to the log


@pytest.mark.parametrize(
    "message",
    [
        "Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the "
        "authentication.",
        "Sign in to confirm you’re not a bot. This helps protect our community. Learn more",
        "Unable to download API page: HTTP Error 429: Too Many Requests",
    ],
)
def test_youtube_blocks_this_network(message: str) -> None:
    """PLA_YOUTUBE §5: YouTube refuses the IP address for a while; a new version would not help."""
    error = translate(_extractor(message))
    assert isinstance(error, youtube.YoutubeBlockedError) and error.message_key == youtube.ERROR_BLOCKED


def _response(code: int) -> object:
    class Response:
        status = code
        reason = "Too Many Requests" if code == 429 else "Forbidden"
        url = "https://www.youtube.com/youtubei/v1/player"
        headers: dict[str, str] = {}  # noqa: RUF012

        def close(self) -> None: ...

    return Response()


def test_too_many_requests_is_a_block() -> None:
    assert _key(_wrapped(HTTPError(_response(429)))) == youtube.ERROR_BLOCKED  # type: ignore[arg-type]


def test_http_errors_from_youtube() -> None:
    class Response:
        status = 403
        reason = "Forbidden"
        url = "https://rr1.googlevideo.com/videoplayback"
        headers: dict[str, str] = {}  # noqa: RUF012

        def close(self) -> None: ...

    assert _key(_wrapped(HTTPError(Response()))) == youtube.ERROR_BROKEN  # type: ignore[arg-type]


def test_unexpected_exceptions_mean_youtube_changed() -> None:
    error = translate(KeyError("streamingData"))
    assert isinstance(error, youtube.YoutubeBrokenError) and "streamingData" in error.detail


def test_our_own_errors_pass_through() -> None:
    inner = youtube.YoutubeTooLongError("1300 s")
    assert translate(_wrapped(inner)) is inner


@pytest.mark.parametrize("number", [28, 13])  # ENOSPC, EACCES
def test_writing_errors_are_raised_as_they_are(number: int) -> None:
    disk = OSError(number, "No space left on device" if number == 28 else "Permission denied")
    assert translate(_wrapped(disk)) is disk


def test_call_translates_and_keeps_the_cause() -> None:
    def failing() -> None:
        raise _extractor("Private video")

    with pytest.raises(youtube.YoutubeUnavailableError) as error:
        call(failing)
    assert isinstance(error.value.__cause__, DownloadError)


def test_call_lets_cancellation_through() -> None:
    def cancelled() -> None:
        raise CancelledError

    with pytest.raises(CancelledError):
        call(cancelled)


def test_translate_survives_cycles() -> None:
    first = RuntimeError("a")
    second = RuntimeError("b")
    first.__context__ = second
    second.__context__ = first
    assert _key(first) == youtube.ERROR_BROKEN
