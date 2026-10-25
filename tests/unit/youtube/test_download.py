"""C03: download_audio with the fake backend: progress, limits, cancellation and errors (contract §15)."""

from __future__ import annotations

import threading
from concurrent.futures import CancelledError
from pathlib import Path

import pytest

from passimaker import youtube
from passimaker.common import CancelToken
from passimaker.model import defaults
from passimaker.youtube.backend import DownloadHook, Info
from passimaker.youtube.consent import ConsentToken
from passimaker.youtube.download import FOLDER_PREFIX
from tests.fakes.youtube import FakeYoutubeBackend, video_info

ID = "aqz-KE-bpKQ"


@pytest.fixture
def video(fake: FakeYoutubeBackend) -> FakeYoutubeBackend:
    fake.add(video_info(ID, title="Big Buck Bunny", duration=596.5, ext="webm"))
    return fake


def _left(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*"))


def test_download_returns_the_original_audio(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    path = youtube.download_audio(token, ID, tmp_path, backend=video)
    assert path.is_file() and path.suffix == ".webm" and path.stat().st_size == video.audio_size
    assert path.parent.parent == tmp_path and path.parent.name.startswith(FOLDER_PREFIX)
    assert _left(tmp_path) == [path.parent, path]
    assert video.calls == [f"extract_info {youtube.watch_url(ID)} flat=False", f"download {ID}"]


def test_two_downloads_of_the_same_video_do_not_collide(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    first = youtube.download_audio(token, ID, tmp_path, backend=video)
    second = youtube.download_audio(token, ID, tmp_path, backend=video)
    assert first != second and first.is_file() and second.is_file()


@pytest.mark.parametrize("report_total", [True, False])
def test_progress_never_goes_back_and_ends_at_the_total(
    report_total: bool, token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    video.report_total = report_total  # False: only an estimate, larger than the real size
    calls: list[tuple[int, int]] = []
    youtube.download_audio(token, ID, tmp_path, progress=lambda d, t: calls.append((d, t)), backend=video)
    assert len(calls) > 3
    done = [d for d, _ in calls]
    assert done == sorted(done)
    assert all(0 <= d <= t for d, t in calls)
    assert calls[-1][0] == calls[-1][1] >= video.audio_size


def test_too_long_is_refused_before_downloading(
    token: ConsentToken, fake: FakeYoutubeBackend, tmp_path: Path
) -> None:
    fake.add(video_info(ID, duration=defaults.YOUTUBE_MAX_DURATION_S + 0.5))
    with pytest.raises(youtube.YoutubeTooLongError) as error:
        youtube.download_audio(token, ID, tmp_path, backend=fake)
    assert error.value.message_key == youtube.ERROR_TOO_LONG
    assert f"download {ID}" not in fake.calls and _left(tmp_path) == []


def test_exactly_the_maximum_is_accepted(
    token: ConsentToken, fake: FakeYoutubeBackend, tmp_path: Path
) -> None:
    fake.add(video_info(ID, duration=float(defaults.YOUTUBE_MAX_DURATION_S)))
    assert youtube.download_audio(token, ID, tmp_path, backend=fake).is_file()


def test_unknown_duration_is_accepted(token: ConsentToken, fake: FakeYoutubeBackend, tmp_path: Path) -> None:
    fake.add(video_info(ID, duration=None))
    assert youtube.download_audio(token, ID, tmp_path, backend=fake).is_file()


@pytest.mark.parametrize("live_status", ["is_live", "is_upcoming"])
def test_live_streams_are_refused(
    live_status: str, token: ConsentToken, fake: FakeYoutubeBackend, tmp_path: Path
) -> None:
    fake.add(video_info(ID, duration=None, live_status=live_status))
    with pytest.raises(youtube.YoutubeUnavailableError) as error:
        youtube.download_audio(token, ID, tmp_path, backend=fake)
    assert error.value.message_key == youtube.ERROR_LIVE
    assert f"download {ID}" not in fake.calls and _left(tmp_path) == []


def test_a_finished_live_stream_is_a_normal_video(
    token: ConsentToken, fake: FakeYoutubeBackend, tmp_path: Path
) -> None:
    fake.add(video_info(ID, live_status="was_live"))
    assert youtube.download_audio(token, ID, tmp_path, backend=fake).is_file()


def test_cancelled_before_starting(token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path) -> None:
    cancel = CancelToken()
    cancel.cancel()
    with pytest.raises(CancelledError):
        youtube.download_audio(token, ID, tmp_path, cancel=cancel, backend=video)
    assert video.calls == [] and _left(tmp_path) == []


def test_cancelled_halfway_leaves_no_file(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    cancel = CancelToken()
    chunks: list[int] = []

    def on_chunk(index: int) -> None:
        chunks.append(index)
        if index == 2:
            cancel.cancel()

    video.on_chunk = on_chunk
    with pytest.raises(CancelledError):
        youtube.download_audio(token, ID, tmp_path, cancel=cancel, backend=video)
    assert chunks == [0, 1, 2]  # stopped at the next block of data
    assert _left(tmp_path) == []


def test_cancelled_from_another_thread(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    cancel = CancelToken()
    started = threading.Event()
    go_on = threading.Event()

    def on_chunk(index: int) -> None:
        started.set()
        go_on.wait(5)

    video.on_chunk = on_chunk
    outcome: list[BaseException] = []

    def work() -> None:
        try:
            youtube.download_audio(token, ID, tmp_path, cancel=cancel, backend=video)
        except BaseException as error:
            outcome.append(error)

    worker = threading.Thread(target=work)
    worker.start()
    assert started.wait(5)
    cancel.cancel()
    go_on.set()
    worker.join(5)
    assert len(outcome) == 1 and isinstance(outcome[0], CancelledError)
    assert _left(tmp_path) == []


def test_cancellation_wrapped_by_yt_dlp_is_still_a_cancellation(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    """yt-dlp may catch the hook's exception and raise its own: the cancel token decides."""
    cancel = CancelToken()

    class Wrapping(FakeYoutubeBackend):
        def download(self, info: Info, folder: Path, hook: DownloadHook) -> Path:
            try:
                return super().download(info, folder, hook)
            except CancelledError as error:
                raise RuntimeError("ERROR: interrupted") from error

    backend = Wrapping(videos=video.videos, on_chunk=lambda i: cancel.cancel())
    with pytest.raises(CancelledError):
        youtube.download_audio(token, ID, tmp_path, cancel=cancel, backend=backend)
    assert _left(tmp_path) == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConnectionResetError(104, "Connection reset by peer"), youtube.YoutubeOfflineError),
        (
            RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden"),
            youtube.YoutubeBrokenError,
        ),
    ],
)
def test_download_errors_leave_no_file(
    error: Exception,
    expected: type[youtube.YoutubeError],
    token: ConsentToken,
    video: FakeYoutubeBackend,
    tmp_path: Path,
) -> None:
    video.errors[f"download:{ID}"] = error
    with pytest.raises(expected):
        youtube.download_audio(token, ID, tmp_path, backend=video)
    assert _left(tmp_path) == []


def test_disk_full_is_not_a_youtube_error(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    video.errors[f"download:{ID}"] = OSError(28, "No space left on device")
    with pytest.raises(OSError) as error:
        youtube.download_audio(token, ID, tmp_path, backend=video)
    assert not isinstance(error.value, youtube.YoutubeError) and error.value.errno == 28
    assert _left(tmp_path) == []


def test_unavailable_video(token: ConsentToken, fake: FakeYoutubeBackend, tmp_path: Path) -> None:
    with pytest.raises(youtube.YoutubeUnavailableError):
        youtube.download_audio(token, ID, tmp_path, backend=fake)


def test_a_file_outside_the_folder_is_not_accepted(
    token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.m4a"

    class Lost(FakeYoutubeBackend):
        def download(self, info: Info, folder: Path, hook: DownloadHook) -> Path:
            elsewhere.write_bytes(b"x")
            return elsewhere

    with pytest.raises(youtube.YoutubeBrokenError):
        youtube.download_audio(token, ID, tmp_path, backend=Lost(videos=video.videos))
    assert _left(tmp_path) == [elsewhere]


def test_wrong_video_id(token: ConsentToken, video: FakeYoutubeBackend, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        youtube.download_audio(token, "../../etc", tmp_path, backend=video)
    assert video.calls == []
