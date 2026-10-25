"""C05: the "Música de YouTube" window (ESPECIFICACIO §1.7 bis, PLA_YOUTUBE §2), with the fake backend.

The network is blocked in every test (socket.socket.connect, socket.create_connection and
socket.getaddrinfo fail and record the attempt) and each test checks at the end that nothing tried.
"""

from __future__ import annotations

import errno
import io
import shutil
import socket
import sys
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QToolButton
from pytestqt.qtbot import QtBot

from passimaker.common import CancelToken, ProgressCallback
from passimaker.ffmpeg import FfmpegError, Mp3Tags
from passimaker.i18n import message
from passimaker.model import defaults
from passimaker.ui.main_window import MainWindow
from passimaker.ui.project_files import user_settings
from passimaker.ui.youtube_dialog import (
    LAST_FOLDER_KEY,
    DownloadJob,
    DownloadRow,
    NoticeDialog,
    Stage,
    YoutubeWindow,
    ensure_consent,
    looks_like_link,
)
from passimaker.youtube import (
    SearchResult,
    YoutubeBlockedError,
    YoutubeBrokenError,
    YoutubeOfflineError,
    YoutubeUnavailableError,
    consent,
)
from tests.fakes.youtube import FakeYoutubeBackend, numbered_id, search_entry, video_info
from tests.ui.helpers import write_song

pytestmark = pytest.mark.ui

ID = "dQw4w9WgXcQ"
WAIT_MS = 5_000


class NetworkAttemptError(AssertionError):
    pass


@pytest.fixture(autouse=True)
def network_attempts(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """No test may open a connection (§2.0): every attempt fails and is recorded."""
    attempts: list[str] = []

    def blocked(name: str) -> Any:
        def refuse(*args: object, **kwargs: object) -> Any:
            attempts.append(name)
            raise NetworkAttemptError(f"network attempt: {name}")

        return refuse

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("getaddrinfo"))
    yield attempts
    assert attempts == []


@pytest.fixture(autouse=True)
def no_consent() -> Iterator[None]:
    consent.revoke()
    yield
    consent.revoke()


@pytest.fixture(autouse=True)
def isolated_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary download folders go here, so the tests can check nothing is left."""
    folder = tmp_path / "temp"
    folder.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(folder))
    return folder


class FakeQuestions:
    def __init__(
        self, accept: bool = True, folder: Path | None = None, cancel_downloads: bool = True
    ) -> None:
        self.accept = accept
        self.folder = folder
        self.cancel_downloads = cancel_downloads
        self.notices = 0
        self.suggested: list[Path] = []
        self.asked_cancel: list[int] = []

    def accept_notice(self) -> bool:
        self.notices += 1
        return self.accept

    def choose_download_folder(self, suggested: Path) -> Path | None:
        self.suggested.append(suggested)
        return self.folder

    def confirm_cancel_downloads(self, count: int) -> bool:
        self.asked_cancel.append(count)
        return self.cancel_downloads


class FakeConverter:
    """Writes a small file instead of calling FFmpeg; `gate` holds it, `error` makes it fail."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, int, Mp3Tags]] = []
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.error: BaseException | None = None

    def __call__(
        self,
        source: Path,
        dest: Path,
        bitrate_kbps: int,
        tags: Mp3Tags,
        progress: ProgressCallback | None = None,
        cancel: CancelToken | None = None,
    ) -> None:
        assert source.is_file()
        self.calls.append((source, dest, bitrate_kbps, tags))
        self.started.set()
        if self.gate is not None:
            while not self.gate.wait(0.01):
                if cancel is not None and cancel.cancelled:
                    return
        if self.error is not None:
            raise self.error
        if cancel is not None and cancel.cancelled:
            return
        if progress is not None:
            progress(1, 2)
        dest.write_bytes(b"mp3")
        if progress is not None:
            progress(2, 2)


class WavBackend(FakeYoutubeBackend):
    """Downloads a real WAV, so the real convert_to_mp3 and the song loader can read it."""

    wav: Path | None = None

    def download(
        self, info: Mapping[str, Any], folder: Path, hook: Callable[[Mapping[str, Any]], None]
    ) -> Path:
        assert self.wav is not None
        target = folder / f"{info['id']}.wav"
        shutil.copyfile(self.wav, target)
        size = target.stat().st_size
        hook({"status": "finished", "downloaded_bytes": size, "total_bytes": size})
        return target


def thumbnail_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), (200, 30, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def backend_with_results(count: int = 25) -> FakeYoutubeBackend:
    fake = FakeYoutubeBackend()
    fake.search_entries = [search_entry(numbered_id(i), f"Cançó {i}") for i in range(count)]
    for i in range(count):
        fake.add(video_info(numbered_id(i), f"Cançó {i}", duration=200.0))
    return fake


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    made = tmp_path / "Música"
    made.mkdir()
    return made


@pytest.fixture
def added() -> list[list[Path]]:
    return []


def make_window(
    qtbot: QtBot,
    backend: FakeYoutubeBackend,
    questions: FakeQuestions,
    added: list[list[Path]],
    convert: FakeConverter | None = None,
) -> YoutubeWindow:
    consent.grant()
    window = YoutubeWindow(
        questions,
        lambda paths: added.append(list(paths)),
        backend=backend,
        convert=convert if convert is not None else FakeConverter(),
    )
    qtbot.addWidget(window)
    window.show()
    return window


def run_search(qtbot: QtBot, window: YoutubeWindow, text: str) -> None:
    window.query.setText(text)
    window.start_search()
    qtbot.waitUntil(lambda: not window.busy, timeout=WAIT_MS)


def select(window: YoutubeWindow, rows: Sequence[int]) -> None:
    for row in rows:
        window.results.item(row).setSelected(True)


def wait_finished(qtbot: QtBot, window: YoutubeWindow) -> None:
    qtbot.waitUntil(lambda: window.download_rows() and window.active_downloads() == 0, timeout=WAIT_MS)


# --- The notice ----------------------------------------------------------------------------------


def test_notice_box_starts_unticked_and_accept_is_disabled_until_ticked(qtbot: QtBot) -> None:
    dialog = NoticeDialog()
    qtbot.addWidget(dialog)
    assert not dialog.agree.isChecked()
    assert not dialog.accept_button.isEnabled()
    dialog.agree.setChecked(True)
    assert dialog.accept_button.isEnabled()
    dialog.agree.setChecked(False)
    assert not dialog.accept_button.isEnabled()
    dialog.accept()  # Enter with the box unticked does nothing
    assert dialog.result() != NoticeDialog.DialogCode.Accepted
    assert "drets d'autor" in " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert consent.current() is None
    assert "yt_dlp" not in sys.modules


def test_notice_cancel_rejects(qtbot: QtBot) -> None:
    dialog = NoticeDialog()
    qtbot.addWidget(dialog)
    dialog.agree.setChecked(True)
    dialog.cancel_button.click()
    assert dialog.result() == NoticeDialog.DialogCode.Rejected


def test_cancelling_the_notice_opens_nothing_and_grants_nothing(window: MainWindow) -> None:
    questions = FakeQuestions(accept=False)
    window.youtube_questions = questions
    window.youtube_backend = FakeYoutubeBackend()
    window.music_youtube_action.trigger()
    assert questions.notices == 1
    assert window.youtube_window is None
    assert consent.current() is None
    assert "yt_dlp" not in sys.modules
    settings = user_settings()
    assert not [key for key in settings.allKeys() if "consent" in key.lower() or "conformitat" in key.lower()]


def test_consent_lasts_for_the_run_and_is_not_saved(window: MainWindow) -> None:
    questions = FakeQuestions()
    window.youtube_questions = questions
    window.youtube_backend = FakeYoutubeBackend()
    window.music_youtube_action.trigger()
    assert window.youtube_window is not None and window.youtube_window.isVisible()
    assert consent.current() is not None
    window.youtube_window.close()
    window.music_youtube_action.trigger()
    assert questions.notices == 1  # not asked again in the same run
    assert window.youtube_window.isVisible()
    assert all("consent" not in key.lower() for key in user_settings().allKeys())
    consent.revoke()  # a new run of the program
    assert ensure_consent(FakeQuestions(accept=False)) is None


def test_opening_the_window_does_not_connect(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = FakeYoutubeBackend()
    make_window(qtbot, fake, FakeQuestions(), added)
    qtbot.wait(50)
    assert fake.calls == []


def test_withdrawing_the_consent_closes_cancels_and_asks_again(
    qtbot: QtBot, folder: Path, added: list[list[Path]]
) -> None:
    fake = backend_with_results(3)
    gate = threading.Event()
    fake.on_chunk = lambda _index: gate.wait(0.02)
    questions = FakeQuestions(folder=folder)
    window = make_window(qtbot, fake, questions, added)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    window.withdraw_button.click()
    gate.set()
    assert not window.isVisible()
    assert consent.current() is None
    assert questions.asked_cancel == []  # withdrawing does not ask
    wait_finished(qtbot, window)
    assert window.download_rows()[0].stage is Stage.CANCELLED
    assert list(folder.iterdir()) == []
    assert added == []
    questions.accept = False
    window.query.setText("einaudi")
    window.start_search()
    assert questions.notices == 1  # asked again, and refused: nothing is searched
    assert window.results.count() == 0


# --- The menu ------------------------------------------------------------------------------------


def test_music_button_is_a_menu_with_files_and_youtube(window: MainWindow) -> None:
    texts = [action.text() for action in window.music_menu.actions()]
    assert texts == ["Des de fitxers…", "Des de YouTube…"]
    assert window.add_music_action.menu() is window.music_menu
    assert window.music_strip.add_button.menu() is window.music_menu
    button = window.toolbar.widgetForAction(window.add_music_action)
    assert isinstance(button, QToolButton)
    assert button.popupMode() is QToolButton.ToolButtonPopupMode.InstantPopup


# --- Searching -----------------------------------------------------------------------------------


def test_search_lists_ten_results_with_thumbnail_title_channel_and_duration(
    qtbot: QtBot, added: list[list[Path]]
) -> None:
    fake = backend_with_results()
    fake.thumbnails[f"https://i.ytimg.com/vi/{numbered_id(0)}/mqdefault.jpg"] = thumbnail_bytes()
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "Ludovico Einaudi Nuvole Bianche")
    rows = window.result_rows()
    assert len(rows) == defaults.YOUTUBE_RESULTS_PER_PAGE
    assert rows[0].title.text() == "Cançó 0"
    assert rows[0].details.text() == "Canal · 3:20"
    pixmap = rows[0].thumbnail.pixmap()
    assert not pixmap.isNull() and pixmap.width() == 160
    assert rows[1].thumbnail.pixmap().isNull()  # its thumbnail failed: the row stays
    assert window.more_button.isVisible()
    assert "extract_info ytsearch10:Ludovico Einaudi Nuvole Bianche flat=True" in fake.calls


def test_more_results_adds_the_next_ten(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = backend_with_results(15)
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "einaudi")
    window.more_button.click()
    qtbot.waitUntil(lambda: not window.busy, timeout=WAIT_MS)
    titles = [row.title.text() for row in window.result_rows()]
    assert titles == [f"Cançó {i}" for i in range(15)]
    assert not window.more_button.isVisible()  # only five more: nothing beyond


def test_no_results(qtbot: QtBot, added: list[list[Path]]) -> None:
    window = make_window(qtbot, FakeYoutubeBackend(), FakeQuestions(), added)
    run_search(qtbot, window, "res de res")
    assert window.results.count() == 0
    assert window.message_label.text() == "No s'ha trobat cap resultat."


def test_a_pasted_link_shows_its_video(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = FakeYoutubeBackend()
    fake.add(video_info(ID, "Nuvole bianche", duration=357.0))
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, f"https://youtu.be/{ID}?t=30")
    rows = window.result_rows()
    assert [row.title.text() for row in rows] == ["Nuvole bianche"]
    assert rows[0].details.text() == "Ludovico Einaudi · 5:57"
    assert not window.more_button.isVisible()
    assert not any(call.startswith("extract_info ytsearch") for call in fake.calls)


def test_an_invalid_link_is_not_searched(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = FakeYoutubeBackend()
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "https://vimeo.com/12345")
    assert window.message_label.text() == message("youtube.invalid_link")
    assert fake.calls == []


def test_looks_like_link() -> None:
    assert looks_like_link("https://example.com/x")
    assert looks_like_link("www.youtube.com/watch")
    assert looks_like_link("vimeo.com/123")
    assert not looks_like_link("Ludovico Einaudi")
    assert not looks_like_link("AC/DC")


def test_live_and_long_videos_are_grey_with_the_reason_and_not_selectable(
    qtbot: QtBot, added: list[list[Path]]
) -> None:
    fake = FakeYoutubeBackend()
    long_entry = search_entry(numbered_id(1), "Mescla de 3 hores", duration=3 * 3600.0)
    live_entry = search_entry(numbered_id(2), "En directe", duration=None)
    live_entry["live_status"] = "is_live"
    fake.search_entries = [search_entry(numbered_id(0), "Normal"), long_entry, live_entry]
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "einaudi")
    normal, long_row, live_row = window.result_rows()
    assert normal.downloadable and not normal.reason_label.isVisibleTo(normal)
    assert long_row.reason_label.text() == message("youtube.too_long")
    assert live_row.reason_label.text() == message("youtube.live")
    assert not long_row.title.isEnabled() and not live_row.title.isEnabled()
    select(window, [0, 1, 2])
    assert window.selected_results() == [normal.result]


def test_open_on_youtube_opens_the_browser(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = backend_with_results(2)
    window = make_window(qtbot, fake, FakeQuestions(), added)
    opened: list[QUrl] = []
    window.open_url = opened.append
    run_search(qtbot, window, "einaudi")
    calls = len(fake.calls)
    window.result_rows()[1].open_button.click()
    assert [url.toString() for url in opened] == [f"https://www.youtube.com/watch?v={numbered_id(1)}"]
    assert len(fake.calls) == calls  # the program itself does not connect


@pytest.mark.parametrize(
    "error",
    [
        YoutubeOfflineError(),
        YoutubeUnavailableError(),
        YoutubeBrokenError("detall per al registre"),
        YoutubeBlockedError("HTTP 429"),
    ],
)
def test_search_errors_show_their_message(qtbot: QtBot, added: list[list[Path]], error: Exception) -> None:
    fake = FakeYoutubeBackend()
    fake.errors["ytsearch10:einaudi"] = error
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "einaudi")
    assert window.message_label.text() == message(error.message_key)  # type: ignore[attr-defined]


def test_a_raw_network_error_is_offline(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = FakeYoutubeBackend()
    fake.errors["ytsearch10:einaudi"] = ConnectionError("Failed to resolve")
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "einaudi")
    assert window.message_label.text() == message("youtube.offline")


def test_link_to_an_unavailable_video(qtbot: QtBot, added: list[list[Path]]) -> None:
    window = make_window(qtbot, FakeYoutubeBackend(), FakeQuestions(), added)
    run_search(qtbot, window, f"https://www.youtube.com/watch?v={ID}")
    assert window.message_label.text() == message("youtube.unavailable")


def test_a_new_search_replaces_the_results(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = backend_with_results(3)
    window = make_window(qtbot, fake, FakeQuestions(), added)
    run_search(qtbot, window, "einaudi")
    fake.search_entries = [search_entry(numbered_id(9), "Una altra")]
    run_search(qtbot, window, "una altra")
    assert [row.title.text() for row in window.result_rows()] == ["Una altra"]


# --- Downloading ---------------------------------------------------------------------------------


def test_download_asks_the_folder_converts_and_adds_to_the_project(
    qtbot: QtBot, folder: Path, added: list[list[Path]], isolated_temp: Path
) -> None:
    fake = backend_with_results(3)
    convert = FakeConverter()
    questions = FakeQuestions(folder=folder)
    window = make_window(qtbot, fake, questions, added, convert)
    run_search(qtbot, window, "einaudi")
    select(window, [0, 2])
    assert window.download_button.isEnabled()
    window.download_button.click()
    wait_finished(qtbot, window)
    assert [row.stage for row in window.download_rows()] == [Stage.DONE, Stage.DONE]
    assert sorted(path.name for path in folder.iterdir()) == ["Cançó 0.mp3", "Cançó 2.mp3"]
    assert sorted(paths[0].name for paths in added) == ["Cançó 0.mp3", "Cançó 2.mp3"]
    _source, dest, bitrate, tags = convert.calls[0]
    assert bitrate == defaults.YOUTUBE_MP3_BITRATE_KBPS
    assert tags.artist == "Canal" and tags.comment.startswith("https://www.youtube.com/watch?v=")
    assert dest.parent == folder
    assert list(isolated_temp.iterdir()) == []  # the original audio is gone
    assert user_settings().value(LAST_FOLDER_KEY) == str(folder)
    assert window.suggested_folder() == folder


def test_first_suggested_folder_is_documents(qtbot: QtBot, added: list[list[Path]]) -> None:
    window = make_window(qtbot, FakeYoutubeBackend(), FakeQuestions(), added)
    assert window.suggested_folder().is_absolute()
    assert user_settings().value(LAST_FOLDER_KEY) is None


def test_cancelling_the_folder_downloads_nothing(qtbot: QtBot, added: list[list[Path]]) -> None:
    fake = backend_with_results(2)
    questions = FakeQuestions(folder=None)
    window = make_window(qtbot, fake, questions, added)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    assert len(questions.suggested) == 1
    assert window.download_rows() == []
    assert not any(call.startswith("download") for call in fake.calls)


def test_without_add_to_project_the_song_is_only_saved(
    qtbot: QtBot, folder: Path, added: list[list[Path]]
) -> None:
    window = make_window(qtbot, backend_with_results(1), FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "einaudi")
    window.add_to_project.setChecked(False)
    select(window, [0])
    window.download_selected()
    wait_finished(qtbot, window)
    assert (folder / "Cançó 0.mp3").is_file()
    assert added == []


def test_same_title_twice_gets_two_names(qtbot: QtBot, folder: Path, added: list[list[Path]]) -> None:
    fake = FakeYoutubeBackend()
    fake.search_entries = [search_entry(numbered_id(i), "Igual") for i in range(2)]
    for i in range(2):
        fake.add(video_info(numbered_id(i), "Igual"))
    (folder / "Igual.mp3").write_bytes(b"de l'usuari")
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "igual")
    select(window, [0, 1])
    window.download_selected()
    wait_finished(qtbot, window)
    assert sorted(path.name for path in folder.iterdir()) == ["Igual (2).mp3", "Igual (3).mp3", "Igual.mp3"]
    assert (folder / "Igual.mp3").read_bytes() == b"de l'usuari"


def test_two_downloads_at_a_time_the_rest_wait(qtbot: QtBot, folder: Path, added: list[list[Path]]) -> None:
    fake = backend_with_results(4)
    gate = threading.Event()
    fake.on_chunk = lambda _index: gate.wait(WAIT_MS / 1000)
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "einaudi")
    select(window, [0, 1, 2, 3])
    window.download_selected()
    rows = window.download_rows()
    qtbot.waitUntil(lambda: sum(row.stage is Stage.DOWNLOADING for row in rows) == 2, timeout=WAIT_MS)
    qtbot.wait(100)
    assert [row.stage for row in rows].count(Stage.QUEUED) == 2
    assert rows[2].status.text() == "A la cua"
    gate.set()
    wait_finished(qtbot, window)
    assert all(row.stage is Stage.DONE for row in rows)


def test_progress_goes_through_downloading_converting_done(
    qtbot: QtBot, folder: Path, added: list[list[Path]]
) -> None:
    fake = backend_with_results(1)
    convert = FakeConverter()
    convert.gate = threading.Event()
    downloading = threading.Event()
    fake.on_chunk = lambda index: downloading.wait(WAIT_MS / 1000) if index == 3 else None
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added, convert)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    row = window.download_rows()[0]
    qtbot.waitUntil(lambda: row.stage is Stage.DOWNLOADING and row.bar.value() > 0, timeout=WAIT_MS)
    assert row.status.text() == "Descarregant…"
    downloading.set()
    qtbot.waitUntil(lambda: row.stage is Stage.CONVERTING, timeout=WAIT_MS)
    assert row.status.text() == "Convertint…"
    convert.gate.set()
    wait_finished(qtbot, window)
    assert row.status.text() == "Fet" and row.bar.value() == row.bar.maximum()
    assert row.show_button.isVisible() and not row.cancel_button.isVisible()


def test_show_in_folder(qtbot: QtBot, folder: Path, added: list[list[Path]]) -> None:
    window = make_window(qtbot, backend_with_results(1), FakeQuestions(folder=folder), added)
    opened: list[QUrl] = []
    window.open_url = opened.append
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    wait_finished(qtbot, window)
    window.download_rows()[0].show_button.click()
    assert [Path(url.toLocalFile()) for url in opened] == [folder]


def test_cancel_one_row_while_downloading(
    qtbot: QtBot, folder: Path, added: list[list[Path]], isolated_temp: Path
) -> None:
    fake = backend_with_results(2)
    started = threading.Event()
    hold = threading.Event()

    def on_chunk(_index: int) -> None:
        started.set()
        hold.wait(0.02)

    fake.on_chunk = on_chunk
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "einaudi")
    select(window, [0, 1])
    window.download_selected()
    first, second = window.download_rows()
    qtbot.waitUntil(lambda: first.stage is Stage.DOWNLOADING, timeout=WAIT_MS)
    first.cancel_button.click()
    wait_finished(qtbot, window)
    assert first.stage is Stage.CANCELLED and first.status.text() == "Cancel·lada"
    assert second.stage is Stage.DONE
    assert [path.name for path in folder.iterdir()] == ["Cançó 1.mp3"]
    assert [paths[0].name for paths in added] == ["Cançó 1.mp3"]
    assert list(isolated_temp.iterdir()) == []


def test_cancel_a_queued_row(qtbot: QtBot, folder: Path, added: list[list[Path]]) -> None:
    fake = backend_with_results(3)
    gate = threading.Event()
    fake.on_chunk = lambda _index: gate.wait(WAIT_MS / 1000)
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "einaudi")
    select(window, [0, 1, 2])
    window.download_selected()
    rows = window.download_rows()
    rows[2].cancel_button.click()
    assert rows[2].stage is Stage.CANCELLED
    gate.set()
    wait_finished(qtbot, window)
    assert [row.stage for row in rows] == [Stage.DONE, Stage.DONE, Stage.CANCELLED]
    assert f"download {numbered_id(2)}" not in fake.calls


def test_cancel_while_converting_leaves_no_file(qtbot: QtBot, folder: Path, added: list[list[Path]]) -> None:
    convert = FakeConverter()
    convert.gate = threading.Event()  # never set: only the cancellation ends it
    window = make_window(qtbot, backend_with_results(1), FakeQuestions(folder=folder), added, convert)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    row = window.download_rows()[0]
    qtbot.waitUntil(lambda: row.stage is Stage.CONVERTING, timeout=WAIT_MS)
    row.cancel_button.click()
    wait_finished(qtbot, window)
    assert row.stage is Stage.CANCELLED
    assert list(folder.iterdir()) == []
    assert added == []


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (YoutubeOfflineError(), "youtube.offline"),
        (YoutubeUnavailableError(), "youtube.unavailable"),
        (YoutubeBrokenError("signature"), "youtube.broken"),
        (YoutubeBlockedError("captcha"), "youtube.blocked"),
        (OSError(errno.ENOSPC, "No space left on device"), "ffmpeg.disk_full"),
        (PermissionError(errno.EACCES, "Permission denied"), "ffmpeg.write_error"),
    ],
)
def test_download_errors_show_in_the_row(
    qtbot: QtBot, folder: Path, added: list[list[Path]], error: BaseException, key: str
) -> None:
    fake = backend_with_results(2)
    fake.errors[f"download:{numbered_id(0)}"] = error
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "einaudi")
    select(window, [0, 1])
    window.download_selected()
    wait_finished(qtbot, window)
    failed, fine = window.download_rows()
    assert failed.stage is Stage.FAILED and failed.status.text() == message(key)
    assert fine.stage is Stage.DONE
    assert [paths[0].name for paths in added] == ["Cançó 1.mp3"]


@pytest.mark.parametrize(
    ("live_status", "duration", "key"),
    [("is_live", None, "youtube.live"), ("not_live", 3 * 3600.0, "youtube.too_long")],
)
def test_download_refused_by_youtube_module(
    qtbot: QtBot, folder: Path, added: list[list[Path]], live_status: str, duration: float | None, key: str
) -> None:
    """The search said it was fine, but by the time of the download it is live or too long."""
    fake = backend_with_results(1)
    fake.add(video_info(numbered_id(0), "Cançó 0", duration=duration, live_status=live_status))
    window = make_window(qtbot, fake, FakeQuestions(folder=folder), added)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    wait_finished(qtbot, window)
    assert window.download_rows()[0].status.text() == message(key)
    assert list(folder.iterdir()) == []


def test_conversion_error_shows_in_the_row(qtbot: QtBot, folder: Path, added: list[list[Path]]) -> None:
    convert = FakeConverter()
    convert.error = FfmpegError("ffmpeg.disk_full", "No space left")
    window = make_window(qtbot, backend_with_results(1), FakeQuestions(folder=folder), added, convert)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    wait_finished(qtbot, window)
    assert window.download_rows()[0].status.text() == message("ffmpeg.disk_full")
    assert added == []


def test_consent_withdrawn_elsewhere_asks_again_before_downloading(
    qtbot: QtBot, folder: Path, added: list[list[Path]]
) -> None:
    questions = FakeQuestions(folder=folder)
    window = make_window(qtbot, backend_with_results(1), questions, added)
    run_search(qtbot, window, "einaudi")
    consent.revoke()  # "Retira la conformitat" in another main window
    questions.accept = False
    select(window, [0])
    window.download_selected()
    assert questions.notices == 1
    assert questions.suggested == []
    assert window.download_rows() == []


# --- Closing -------------------------------------------------------------------------------------


def test_closing_with_downloads_asks_and_keeping_them_keeps_the_window(
    qtbot: QtBot, folder: Path, added: list[list[Path]]
) -> None:
    fake = backend_with_results(1)
    gate = threading.Event()
    fake.on_chunk = lambda _index: gate.wait(WAIT_MS / 1000)
    questions = FakeQuestions(folder=folder, cancel_downloads=False)
    window = make_window(qtbot, fake, questions, added)
    run_search(qtbot, window, "einaudi")
    select(window, [0])
    window.download_selected()
    assert not window.close()
    assert questions.asked_cancel == [1]
    assert window.isVisible()
    gate.set()
    wait_finished(qtbot, window)
    assert window.download_rows()[0].stage is Stage.DONE


def test_closing_with_downloads_cancels_them_and_leaves_nothing(
    qtbot: QtBot, folder: Path, added: list[list[Path]], isolated_temp: Path
) -> None:
    fake = backend_with_results(3)
    fake.on_chunk = lambda _index: threading.Event().wait(0.02)
    questions = FakeQuestions(folder=folder, cancel_downloads=True)
    window = make_window(qtbot, fake, questions, added)
    run_search(qtbot, window, "einaudi")
    select(window, [0, 1, 2])
    window.download_selected()
    qtbot.waitUntil(lambda: window.download_rows()[0].stage is Stage.DOWNLOADING, timeout=WAIT_MS)
    assert window.close()
    assert questions.asked_cancel == [3]
    wait_finished(qtbot, window)
    assert all(row.stage is Stage.CANCELLED for row in window.download_rows())
    assert list(folder.iterdir()) == []
    assert list(isolated_temp.iterdir()) == []
    assert added == []


def test_closing_without_downloads_does_not_ask(qtbot: QtBot, added: list[list[Path]]) -> None:
    questions = FakeQuestions()
    window = make_window(qtbot, backend_with_results(1), questions, added)
    assert window.close()
    assert questions.asked_cancel == []


def test_closing_the_main_window_with_downloads_asks_first(
    qtbot: QtBot, window: MainWindow, folder: Path
) -> None:
    fake = backend_with_results(1)
    gate = threading.Event()
    fake.on_chunk = lambda _index: gate.wait(WAIT_MS / 1000)
    questions = FakeQuestions(folder=folder, cancel_downloads=False)
    window.youtube_questions = questions
    window.youtube_backend = fake
    window.music_youtube_action.trigger()
    youtube = window.youtube_window
    assert youtube is not None
    run_search(qtbot, youtube, "einaudi")
    select(youtube, [0])
    youtube.download_selected()
    assert not window.close()
    assert window.isVisible()
    gate.set()
    wait_finished(qtbot, youtube)


# --- Into the project, with the real conversion ---------------------------------------------------


def test_a_downloaded_song_reaches_the_controller_as_add_songs(
    qtbot: QtBot, window: MainWindow, folder: Path, tmp_path: Path
) -> None:
    """The real convert_to_mp3 and the window's add_songs: the song is in the project; Ctrl+Z removes it."""
    fake = WavBackend()
    fake.wav = write_song(tmp_path / "origen.wav", 1.0)
    fake.add(video_info(ID, "Nuvole bianche", duration=1.0))
    window.youtube_questions = FakeQuestions(folder=folder)
    window.youtube_backend = fake
    window.music_youtube_action.trigger()
    youtube = window.youtube_window
    assert youtube is not None
    run_search(qtbot, youtube, f"https://www.youtube.com/watch?v={ID}")
    select(youtube, [0])
    youtube.download_selected()
    qtbot.waitUntil(lambda: len(window.controller.project.music.songs) == 1, timeout=20_000)
    song = window.controller.project.music.songs[0]
    assert song.path == folder / "Nuvole bianche.mp3"
    assert song.path.is_file()
    assert youtube.download_rows()[0].stage is Stage.DONE
    window.undo()
    assert window.controller.project.music.songs == ()


def test_download_row_texts_are_catalan(qtbot: QtBot) -> None:
    result = SearchResult(ID, "Títol", "Canal", 10.0, "", False, f"https://www.youtube.com/watch?v={ID}")
    job = DownloadJob(
        result, Path(), consent.grant(), FakeYoutubeBackend(), FakeConverter(), threading.Lock()
    )
    row = DownloadRow(job)
    qtbot.addWidget(row)
    texts: list[str] = []
    for stage in (Stage.QUEUED, Stage.DOWNLOADING, Stage.CONVERTING, Stage.DONE, Stage.CANCELLED):
        row.set_stage(stage)
        texts.append(row.status.text())
    assert texts == ["A la cua", "Descarregant…", "Convertint…", "Fet", "Cancel·lada"]
