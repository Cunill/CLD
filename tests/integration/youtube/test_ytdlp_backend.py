"""C03: the real backend (yt-dlp as a library) against a local web server, without internet.

YouTube itself cannot be reached from the cloud or the CI (tests marked `xarxa`, test_xarxa.py);
here yt-dlp's generic extractor downloads a tone from 127.0.0.1, which exercises the parts that
are ours: options, progress hook, cancellation, cleaning up, and the conversion that follows.
"""

from __future__ import annotations

import http.server
import threading
import time
from collections.abc import Iterator
from concurrent.futures import CancelledError
from pathlib import Path

import pytest

from passimaker import ffmpeg, youtube
from passimaker.common import CancelToken
from passimaker.youtube.backend import Info, YtDlpBackend
from passimaker.youtube.consent import ConsentToken
from passimaker.youtube.download import FOLDER_PREFIX

ID = "aqz-KE-bpKQ"
PROXY_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")


class _Server:
    def __init__(self, payload: bytes, chunk: int, delay_s: float) -> None:
        self.payload = payload
        self.chunk = chunk
        self.delay_s = delay_s
        self.status = 200
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if server.status != 200:
                    self.send_error(server.status)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "audio/mp4")
                self.send_header("Content-Length", str(len(server.payload)))
                self.end_headers()
                try:
                    for start in range(0, len(server.payload), server.chunk):
                        self.wfile.write(server.payload[start : start + server.chunk])
                        time.sleep(server.delay_s)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/{ID}.m4a"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class LocalBackend(YtDlpBackend):
    """The real backend, but YouTube's watch URL is replaced by the local server's file."""

    def __init__(self, url: str) -> None:
        self.url = url

    def extract_info(self, url: str, *, flat: bool) -> Info:
        info = dict(super().extract_info(self.url, flat=flat))
        info["id"] = ID  # the generic extractor names it after the file
        return info


@pytest.fixture
def tone(fixture_files: dict[str, Path]) -> bytes:
    return fixture_files["tone_440.m4a"].read_bytes()


@pytest.fixture
def server(tone: bytes, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Server]:
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)  # 127.0.0.1 directly, not through the cloud's proxy
    local = _Server(tone, chunk=4096, delay_s=0.0)
    yield local
    local.close()


@pytest.fixture
def token() -> Iterator[ConsentToken]:
    yield youtube.consent.grant()
    youtube.consent.revoke()


def test_download_and_convert(server: _Server, tone: bytes, token: ConsentToken, tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []
    audio = youtube.download_audio(
        token, ID, tmp_path, progress=lambda d, t: calls.append((d, t)), backend=LocalBackend(server.url)
    )
    assert audio.read_bytes() == tone
    assert audio.parent.parent == tmp_path and audio.parent.name.startswith(FOLDER_PREFIX)
    assert [p.name for p in audio.parent.iterdir()] == [audio.name]  # no .part, no .ytdl, no .json
    assert calls and calls[-1] == (len(tone), len(tone))
    assert [d for d, _ in calls] == sorted(d for d, _ in calls)

    target = youtube.safe_target_path(tmp_path, "Big Buck Bunny: to (440 Hz)")
    tags = ffmpeg.Mp3Tags(title="Big Buck Bunny", artist="Blender", comment=youtube.watch_url(ID))
    ffmpeg.convert_to_mp3(audio, target, 192, tags)
    media = ffmpeg.probe(target)
    assert target.name == "Big Buck Bunny to (440 Hz).mp3"
    assert media.has_audio and media.sample_rate == 48000 and media.channels == 2


def test_cancel_during_the_download(
    server: _Server, tone: bytes, token: ConsentToken, tmp_path: Path
) -> None:
    server.payload = tone * 8
    server.delay_s = 0.005  # slow enough to cancel halfway
    cancel = CancelToken()
    seen: list[int] = []

    def progress(done: int, total: int) -> None:
        seen.append(done)
        if done > total // 4:
            cancel.cancel()

    started = time.monotonic()
    with pytest.raises(CancelledError):
        youtube.download_audio(
            token, ID, tmp_path, progress=progress, cancel=cancel, backend=LocalBackend(server.url)
        )
    assert time.monotonic() - started < 10
    assert seen and max(seen) < len(server.payload)
    assert list(tmp_path.iterdir()) == []


def test_missing_file_on_the_server(server: _Server, token: ConsentToken, tmp_path: Path) -> None:
    server.status = 404
    with pytest.raises(youtube.YoutubeUnavailableError):
        youtube.download_audio(token, ID, tmp_path, backend=LocalBackend(server.url))
    assert list(tmp_path.iterdir()) == []


def test_server_gone(server: _Server, token: ConsentToken, tmp_path: Path) -> None:
    url = server.url
    server.close()
    with pytest.raises(youtube.YoutubeOfflineError):
        youtube.download_audio(token, ID, tmp_path, backend=LocalBackend(url))
    assert list(tmp_path.iterdir()) == []


def test_options_never_ask_yt_dlp_to_convert() -> None:
    """Rule 7: FFmpeg only through passimaker.ffmpeg; yt-dlp downloads the stream as it is."""
    options = YtDlpBackend._options()  # pyright: ignore[reportPrivateUsage]
    assert options["postprocessors"] == [] and options["fixup"] == "never"
    assert options["cachedir"] is False and options["noplaylist"] is True
    assert "ffmpeg_location" not in options
