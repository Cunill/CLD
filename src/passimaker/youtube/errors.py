"""Translating yt-dlp's and the network's exceptions into this module's errors (contract §15).

yt-dlp wraps the real cause (ExtractorError, TransportError, socket errors…) inside DownloadError;
`translate` walks that chain. It matches yt-dlp's classes by name, so this module does not import
yt_dlp. The order matters: a recognised message about the video beats a generic network class.
"""

from __future__ import annotations

import errno
import socket
import urllib.error
from collections.abc import Callable, Iterator
from concurrent.futures import CancelledError

from passimaker.common import CancelToken
from passimaker.youtube.types import (
    ERROR_LIVE,
    YoutubeBlockedError,
    YoutubeBrokenError,
    YoutubeError,
    YoutubeOfflineError,
    YoutubeUnavailableError,
)

_LIVE_MESSAGES = (
    "live event will begin",
    "this live event",
    "premieres in",
    "premiere will begin",
    "is a live stream",
    "is live",
)
_UNAVAILABLE_MESSAGES = (
    "video unavailable",
    "this video is unavailable",
    "private video",
    "this video is private",
    "confirm your age",
    "age-restricted",
    "age restricted",
    "inappropriate for some users",
    "not available in your country",
    "available in your country",
    "blocked it in your country",
    "has been removed",
    "has been terminated",
    "members-only",
    "join this channel",
    "requires payment",
    "copyright",
    "http error 404",
    "http error 410",
)
_BLOCKED_MESSAGES = (
    "not a bot",
    "http error 429",
    "too many requests",
)
"""YouTube refuses this IP address for a while (PLA_YOUTUBE §5); not fixable from the program."""
_OFFLINE_MESSAGES = (
    "getaddrinfo failed",
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "no address associated with hostname",
    "failed to resolve",
    "network is unreachable",
    "no route to host",
    "connection refused",
    "connection reset",
    "connection aborted",
    "timed out",
    "unable to connect",
    "failed to establish a new connection",
)
_OFFLINE_CLASSES = {"TransportError", "ProxyError", "SSLError", "CertificateVerifyError", "IncompleteRead"}
"""yt_dlp.networking.exceptions: the request did not get an answer from YouTube."""
_NETWORK_ERRNOS = {
    errno.ENETUNREACH,
    errno.ENETDOWN,
    errno.EHOSTUNREACH,
    errno.EHOSTDOWN,
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ETIMEDOUT,
}
_NETWORK_WINERRORS = {10050, 10051, 10053, 10054, 10060, 10061, 10064, 10065, 11001, 11002, 11003, 11004}
"""WSAENETDOWN… WSAHOST_NOT_FOUND, WSANO_DATA: what Windows reports without a connection."""
_LOCAL_ERRNOS = {errno.ENOSPC, errno.EACCES, errno.EPERM, errno.EROFS, errno.ENAMETOOLONG, errno.ENOENT}
"""Writing the downloaded file failed: not a YouTube problem, the original OSError is raised."""


def call[T](operation: Callable[[], T]) -> T:
    """Runs a backend call, raising this module's errors (`translate`) instead of yt-dlp's.

    CancelledError passes through unchanged.
    """
    try:
        return operation()
    except CancelledError:
        raise
    except Exception as error:
        raise translate(error) from error


def check_cancel(cancel: CancelToken | None) -> None:
    """Raises CancelledError if `cancel` was set: how this module's functions report a cancellation."""
    if cancel is not None and cancel.cancelled:
        raise CancelledError


def translate(error: BaseException) -> BaseException:
    """The exception to raise for `error`: a YoutubeError, or the local OSError behind it.

    - a YoutubeError anywhere in the chain is returned as is;
    - a live stream, then a private/deleted/restricted video (by yt-dlp's message);
    - YouTube refusing this network ("confirm you're not a bot", HTTP 429);
    - no connection (socket errors, yt-dlp's TransportError, or their messages);
    - a file system error while writing (disk full, no permission) is returned unchanged;
    - anything else means yt-dlp no longer understands YouTube: YoutubeBrokenError with the detail.
    """
    chain = list(_chain(error))
    for item in chain:
        if isinstance(item, YoutubeError):
            return item
    detail = " <- ".join(_describe(item) for item in chain)
    text = detail.lower()
    if any(message in text for message in _LIVE_MESSAGES):
        return YoutubeUnavailableError(ERROR_LIVE, detail)
    if any(message in text for message in _UNAVAILABLE_MESSAGES):
        return YoutubeUnavailableError(detail=detail)
    if any(message in text for message in _BLOCKED_MESSAGES) or any(_status(item) == 429 for item in chain):
        return YoutubeBlockedError(detail)
    if any(_is_network(item) for item in chain) or any(message in text for message in _OFFLINE_MESSAGES):
        return YoutubeOfflineError(detail)
    for item in chain:
        local = type(item) is OSError or isinstance(item, PermissionError | FileNotFoundError)
        if local and isinstance(item, OSError) and item.errno in _LOCAL_ERRNOS:
            return item
    return YoutubeBrokenError(detail)


def _chain(error: BaseException) -> Iterator[BaseException]:
    """`error` and every exception it wraps: exc_info (DownloadError), cause (ExtractorError),
    reason (URLError), __cause__ and __context__."""
    seen: list[BaseException] = []
    pending: list[BaseException] = [error]
    while pending:
        item = pending.pop(0)
        if any(item is other for other in seen):
            continue
        seen.append(item)
        yield item
        exc_info: object = getattr(item, "exc_info", None)
        if isinstance(exc_info, tuple) and len(exc_info) == 3:  # pyright: ignore[reportUnknownArgumentType]
            inner: object = exc_info[1]  # pyright: ignore[reportUnknownVariableType]
            if isinstance(inner, BaseException):
                pending.append(inner)
        for name in ("cause", "reason"):
            wrapped: object = getattr(item, name, None)
            if isinstance(wrapped, BaseException):
                pending.append(wrapped)
        for wrapped in (item.__cause__, item.__context__):
            if wrapped is not None:
                pending.append(wrapped)


def _status(error: BaseException) -> object:
    """The HTTP status of yt-dlp's HTTPError (or urllib's), else None."""
    status: object = getattr(error, "status", None)
    return status if status is not None else getattr(error, "code", None)


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _is_network(error: BaseException) -> bool:
    if isinstance(error, socket.gaierror | socket.herror | ConnectionError | TimeoutError):
        return True
    if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError):
        return True
    if any(cls.__name__ in _OFFLINE_CLASSES for cls in type(error).__mro__):
        return True
    if isinstance(error, OSError):
        winerror: object = getattr(error, "winerror", None)
        return error.errno in _NETWORK_ERRNOS or winerror in _NETWORK_WINERRORS
    return False
