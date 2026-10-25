"""C03: no connection before the consent (ESPECIFICACIO §1.7 bis, decision 0012, PLA_YOUTUBE §2.0).

The network is blocked (socket.socket.connect, socket.create_connection and socket.getaddrinfo
fail and record the attempt). The static check that no module outside passimaker.youtube imports
yt_dlp, urllib.request, http.client or socket is tests/unit/test_architecture.py.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from passimaker import youtube
from passimaker.youtube import consent
from passimaker.youtube.consent import ConsentToken
from tests.fakes.youtube import FakeYoutubeBackend, search_entry, video_info

ID = "dQw4w9WgXcQ"
THUMB = f"https://i.ytimg.com/vi/{ID}/mqdefault.jpg"


def _every_network_call(token: object, tmp_path: Path) -> list[object]:
    calls = [
        lambda: youtube.search(token, "Nuvole bianche"),  # type: ignore[arg-type]
        lambda: youtube.resolve(token, ID),  # type: ignore[arg-type]
        lambda: youtube.fetch_thumbnail(token, THUMB),  # type: ignore[arg-type]
        lambda: youtube.download_audio(token, ID, tmp_path),  # type: ignore[arg-type]
    ]
    outcomes: list[object] = []
    for function in calls:
        try:
            outcomes.append(function())
        except youtube.YoutubeConsentError as error:
            outcomes.append(error)
    return outcomes


def test_the_blocker_works(network_attempts: list[str]) -> None:
    with pytest.raises(AssertionError):
        socket.create_connection(("www.youtube.com", 443))
    assert network_attempts


def test_without_consent_nothing_connects(network_attempts: list[str], tmp_path: Path) -> None:
    """The real backend (yt-dlp) and every network function: YoutubeConsentError, no attempt."""
    stale = consent.grant()
    consent.revoke()
    for token in (None, stale, "a forged token"):
        outcomes = _every_network_call(token, tmp_path)
        assert all(isinstance(o, youtube.YoutubeConsentError) for o in outcomes), outcomes
    assert network_attempts == []
    assert list(tmp_path.iterdir()) == []


def test_without_consent_yt_dlp_is_not_even_loaded(tmp_path: Path) -> None:
    """In a fresh process (this one may have yt_dlp loaded by other tests)."""
    code = textwrap.dedent(
        f"""
        import socket, sys
        from pathlib import Path

        attempts = []
        def refuse(*args, **kwargs):
            attempts.append(args)
            raise OSError("blocked")
        socket.socket.connect = refuse
        socket.create_connection = refuse
        socket.getaddrinfo = refuse

        from passimaker import youtube
        from passimaker.youtube import consent
        assert consent.current() is None
        refused = 0
        for call in (
            lambda: youtube.search(None, "x"),
            lambda: youtube.resolve(None, "{ID}"),
            lambda: youtube.fetch_thumbnail(None, "{THUMB}"),
            lambda: youtube.download_audio(None, "{ID}", Path(r"{tmp_path}")),
        ):
            try:
                call()
            except youtube.YoutubeConsentError:
                refused += 1
        print(refused, len(attempts), "yt_dlp" in sys.modules, "deno" in sys.modules)
        """
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["4", "0", "False", "False"]


def test_with_consent_and_the_fake_backend_nothing_connects(
    network_attempts: list[str], token: ConsentToken, tmp_path: Path
) -> None:
    fake = FakeYoutubeBackend(search_entries=[search_entry(ID)], thumbnails={THUMB: b"jpg"})
    fake.add(video_info(ID))
    assert youtube.search(token, "x", backend=fake)
    assert youtube.resolve(token, ID, backend=fake)
    assert youtube.fetch_thumbnail(token, THUMB, backend=fake)
    assert youtube.download_audio(token, ID, tmp_path, backend=fake).is_file()
    assert network_attempts == []


def test_revoking_stops_the_next_call(network_attempts: list[str], token: ConsentToken) -> None:
    fake = FakeYoutubeBackend(search_entries=[search_entry(ID)])
    assert youtube.search(token, "x", backend=fake)
    consent.revoke()  # "Retira la conformitat"
    with pytest.raises(youtube.YoutubeConsentError):
        youtube.search(token, "x", backend=fake)
    assert len(fake.calls) == 1 and network_attempts == []


def test_consent_is_not_saved_anywhere(tmp_path: Path) -> None:
    """A new run of the program (a fresh process) starts without consent, even after granting it."""
    code = (
        "from passimaker.youtube import consent\n"
        "import sys\n"
        "if sys.argv[1] == 'grant':\n"
        "    consent.grant()\n"
        "print(consent.current() is None)\n"
    )
    runs = [
        subprocess.run(
            [sys.executable, "-c", code, arg], capture_output=True, text=True, check=True, cwd=tmp_path
        )
        for arg in ("grant", "check")
    ]
    assert [r.stdout.strip() for r in runs] == ["False", "True"]
    assert list(tmp_path.iterdir()) == []  # nothing written next to it either


def test_the_real_backend_without_network_says_offline(
    monkeypatch: pytest.MonkeyPatch, token: ConsentToken, tmp_path: Path
) -> None:
    """yt-dlp itself, with consent but no network (name resolution fails): YoutubeOfflineError."""
    attempts: list[object] = []

    def no_network(*args: object, **kwargs: object) -> object:
        attempts.append(args)
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(youtube.YoutubeOfflineError):
        youtube.resolve(token, ID)
    with pytest.raises(youtube.YoutubeOfflineError):
        youtube.search(token, "Nuvole bianche", limit=3)
    with pytest.raises(youtube.YoutubeOfflineError):
        youtube.fetch_thumbnail(token, THUMB)
    with pytest.raises(youtube.YoutubeOfflineError):
        youtube.download_audio(token, ID, tmp_path)
    assert attempts  # it did try, and only after the consent
    assert list(tmp_path.iterdir()) == []
