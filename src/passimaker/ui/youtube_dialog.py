"""The "Música de YouTube" window (ESPECIFICACIO §1.7 bis, PLA_YOUTUBE §2, decision 0012, block C05).

- The notice comes first: nothing connects until the user ticks the box and accepts it. The consent
  lives only in passimaker.youtube.consent (memory of this run, shared by every window).
- The window does nothing by itself when it opens: the first connection is the first search or
  link the user asks for.
- One field for a search or a pasted link; results with thumbnail, title, channel and duration;
  live streams and long videos in grey with the reason.
- [Descarrega en MP3] asks for the folder, then downloads two songs at a time (the rest wait in the
  queue): download_audio, then ffmpeg.convert_to_mp3. Every network or disk operation runs in a
  worker thread (rule 6); the results come back to the interface thread through signals.

The window takes the backend (tests/fakes/youtube.py in the tests) and the converter as parameters.
"""

from __future__ import annotations

import errno
import logging
import re
import shutil
import tempfile
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import CancelledError
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, cast

from PySide6.QtCore import QObject, QRunnable, QStandardPaths, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from passimaker.common import CancelToken, PassiMakerError, ProgressCallback
from passimaker.ffmpeg import Mp3Tags, convert_to_mp3
from passimaker.i18n import message
from passimaker.model import defaults
from passimaker.ui.dialogs import DialogQuestions
from passimaker.ui.formatting import clock
from passimaker.ui.project_files import user_settings
from passimaker.youtube import (
    ERROR_BROKEN,
    ERROR_INVALID_LINK,
    ERROR_LIVE,
    ERROR_TOO_LONG,
    ConsentToken,
    SearchResult,
    YoutubeBackend,
    YtDlpBackend,
    consent,
    download_audio,
    fetch_thumbnail,
    parse_link,
    resolve,
    safe_target_path,
    search,
)
from passimaker.youtube.search import MAX_SEARCH_RESULTS

_log = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 90
"""Half of the 320×180 thumbnails YouTube gives (contract §15)."""
LOOKUP_THREADS = 4
"""Searches and thumbnails at the same time (downloads have their own queue)."""
CLOSE_WAIT_MS = 10_000
"""Closing with downloads: cancelled downloads stop within a chunk, conversions within 2 s (C04)."""
LAST_FOLDER_KEY = "youtube/last_folder"
"""The folder of the last download (ESPECIFICACIO §1.7 bis: proposed the next time). Not the consent."""
TEMP_PREFIX = "passimaker_youtube_"
PROGRESS_STEPS = 1000

_LINK_LIKE = re.compile(r"^(https?://|www\.)|^[\w-]+(\.[\w-]+)+/", re.IGNORECASE)
"""Text that is clearly a link (so it is not searched as words): "youtube.com/…", "http://…"."""


def looks_like_link(text: str) -> bool:
    return " " not in text.strip() and _LINK_LIKE.search(text.strip()) is not None


def unavailable_reason(result: SearchResult) -> str | None:
    """Why a result cannot be downloaded (shown in grey), or None."""
    if result.is_live:
        return message(ERROR_LIVE)
    if result.duration_s is not None and result.duration_s > defaults.YOUTUBE_MAX_DURATION_S:
        return message(ERROR_TOO_LONG)
    return None


def error_text(error: BaseException) -> str:
    """The Catalan text of an error: YouTube's and FFmpeg's by key; disk full or no permission as
    a writing error (decision 4 of C03); anything unexpected as "YouTube ha canviat"."""
    if isinstance(error, PassiMakerError):
        return message(error.message_key)
    if isinstance(error, OSError):
        return message("ffmpeg.disk_full" if error.errno == errno.ENOSPC else "ffmpeg.write_error")
    return message(ERROR_BROKEN)


def log_error(what: str, error: BaseException) -> None:
    detail = error.detail if isinstance(error, PassiMakerError) else ""
    _log.warning("YouTube, %s: %r %s", what, error, detail)


# --- Questions --------------------------------------------------------------------------------------


class YoutubeQuestions(Protocol):
    """What the YouTube window asks the user (the tests answer without dialogs)."""

    def accept_notice(self) -> bool:
        """The notice "Abans de fer servir YouTube": True only after ticking the box and accepting."""
        ...

    def choose_download_folder(self, suggested: Path) -> Path | None:
        """[Descarrega en MP3]: the folder for the whole selection, or None (nothing is downloaded)."""
        ...

    def confirm_cancel_downloads(self, count: int) -> bool:
        """Closing with downloads in progress: True cancels them and closes."""
        ...


class NoticeDialog(QDialog):
    """PLA_YOUTUBE §2.0: modal; [Accepta i continua] stays disabled until the box is ticked."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Abans de fer servir YouTube"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        intro = QLabel(
            self.tr("Aquesta funció es connecta a internet per cercar i descarregar àudio de YouTube.")
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        points = (
            self.tr(
                "Les condicions de YouTube no permeten descarregar contingut si YouTube no ofereix "
                "un botó de descàrrega."
            ),
            self.tr(
                "La majoria de cançons tenen drets d'autor. Descarrega i fes servir només música que "
                "tinguis dret a fer servir."
            ),
            self.tr("Ets responsable de l'ús que en facis."),
            self.tr(
                "PassiMaker i els seus autors declinen qualsevol responsabilitat derivada de l'ús de "
                "la música descarregada, i en particular per qualsevol infracció dels drets d'autor o "
                "de les condicions de YouTube."
            ),
        )
        for point in points:
            label = QLabel("· " + point)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.agree = QCheckBox(self.tr("He llegit l'avís, n'accepto les condicions i hi estic conforme"))
        self.agree.setChecked(False)
        layout.addWidget(self.agree)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton(self.tr("Cancel·la"))
        self.accept_button = QPushButton(self.tr("Accepta i continua"))
        self.accept_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.accept_button)
        layout.addLayout(buttons)
        self.agree.toggled.connect(self.accept_button.setEnabled)
        self.cancel_button.clicked.connect(self.reject)
        self.accept_button.clicked.connect(self.accept)
        self.setMinimumWidth(520)

    def accept(self) -> None:
        if self.agree.isChecked():
            super().accept()


class YoutubeDialogs(DialogQuestions):
    """The real questions of the YouTube window, as modal dialogs."""

    def accept_notice(self) -> bool:
        return NoticeDialog(self.parentWidget()).exec() == QDialog.DialogCode.Accepted

    def confirm_cancel_downloads(self, count: int) -> bool:
        answer = QMessageBox.question(
            self.parentWidget(),
            self.tr("Música de YouTube"),
            (
                self.tr("Hi ha 1 descàrrega en curs. La vols cancel·lar?")
                if count == 1
                else self.tr("Hi ha {n} descàrregues en curs. Les vols cancel·lar?").format(n=count)
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes


def ensure_consent(questions: YoutubeQuestions) -> ConsentToken | None:
    """The consent of this run of the program, asking with the notice if there is none yet."""
    token = consent.current()
    if token is not None:
        return token
    if not questions.accept_notice():
        return None
    return consent.grant()


# --- Work in other threads --------------------------------------------------------------------------


class Converter(Protocol):
    """ffmpeg.convert_to_mp3 (contract §8): returns normally after a cancellation."""

    def __call__(
        self,
        source: Path,
        dest: Path,
        bitrate_kbps: int,
        tags: Mp3Tags,
        progress: ProgressCallback | None = None,
        cancel: CancelToken | None = None,
    ) -> None: ...


class _LookupSignals(QObject):
    done = Signal(object, object)
    """(result, error): one of them is None."""


class _Lookup(QRunnable):
    """Any call that may block (search, link, thumbnail), with its answer as a signal."""

    def __init__(self, work: Callable[[], object], signals: _LookupSignals) -> None:
        super().__init__()
        self._work = work
        self._signals = signals

    def run(self) -> None:
        try:
            result = self._work()
        except BaseException as error:  # every failure goes back to the interface
            self._signals.done.emit(None, error)
        else:
            self._signals.done.emit(result, None)


class Stage(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


ACTIVE_STAGES = frozenset({Stage.QUEUED, Stage.DOWNLOADING, Stage.CONVERTING})


class _DownloadSignals(QObject):
    progress = Signal(object, int, int)
    """(stage, done, total) while downloading or converting."""
    finished = Signal(object, object)
    """(path, error): the MP3, or the error (CancelledError if cancelled)."""


@dataclass
class DownloadJob:
    result: SearchResult
    folder: Path
    token: ConsentToken
    backend: YoutubeBackend
    convert: Converter
    names: threading.Lock
    """Held from choosing the free name until the MP3 is there: safe_target_path does not reserve
    the name (C03, decision 7), so two songs with the same title must not convert at once."""
    cancel: CancelToken = field(default_factory=CancelToken)


class _Download(QRunnable):
    def __init__(self, job: DownloadJob, signals: _DownloadSignals) -> None:
        super().__init__()
        self._job = job
        self._signals = signals

    def run(self) -> None:
        job = self._job
        try:
            self._signals.finished.emit(self._work(job), None)
        except BaseException as error:  # every failure goes back to the interface
            self._signals.finished.emit(None, error)

    def _work(self, job: DownloadJob) -> Path:
        if job.cancel.cancelled:
            raise CancelledError
        temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        try:
            source = download_audio(
                job.token,
                job.result.video_id,
                temp_dir,
                lambda done, total: self._signals.progress.emit(Stage.DOWNLOADING, done, total),
                job.cancel,
                backend=job.backend,
            )
            with job.names:
                if job.cancel.cancelled:
                    raise CancelledError
                target = safe_target_path(job.folder, job.result.title)
                self._signals.progress.emit(Stage.CONVERTING, 0, 1)
                tags = Mp3Tags(title=job.result.title, artist=job.result.channel, comment=job.result.url)
                job.convert(
                    source,
                    target,
                    defaults.YOUTUBE_MP3_BITRATE_KBPS,
                    tags,
                    lambda done, total: self._signals.progress.emit(Stage.CONVERTING, done, total),
                    job.cancel,
                )
            if target.is_file():
                return target
            raise CancelledError  # convert_to_mp3 returns without a file only when cancelled (C04)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# --- Rows -------------------------------------------------------------------------------------------


class ResultRow(QWidget):
    """One result: thumbnail, title, channel · duration, the reason it is grey, [Obre a YouTube]."""

    def __init__(self, result: SearchResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result = result
        self.reason = unavailable_reason(result)
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        self.thumbnail.setStyleSheet("background: #ddd;")
        self.title = QLabel(result.title)
        self.title.setWordWrap(True)
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        details = [result.channel] if result.channel else []
        if result.duration_s is not None:
            details.append(clock(result.duration_s))
        self.details = QLabel(" · ".join(details))
        self.reason_label = QLabel(self.reason or "")
        self.reason_label.setVisible(self.reason is not None)
        self.open_button = QPushButton(self.tr("Obre a YouTube"))
        self.open_button.setToolTip(self.tr("Obre el vídeo al navegador per escoltar-lo"))
        texts = QVBoxLayout()
        texts.addWidget(self.title)
        texts.addWidget(self.details)
        texts.addWidget(self.reason_label)
        texts.addStretch(1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.thumbnail)
        layout.addLayout(texts, 1)
        layout.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignVCenter)
        for label in (self.title, self.details, self.reason_label):
            label.setEnabled(self.reason is None)

    @property
    def downloadable(self) -> bool:
        return self.reason is None

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self.thumbnail.setPixmap(pixmap)


class DownloadRow(QWidget):
    """One song of the queue: title, stage, progress, [Cancel·la] and [Mostrar a la carpeta]."""

    def __init__(self, job: DownloadJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.stage = Stage.QUEUED
        self.path: Path | None = None
        self.title = QLabel(job.result.title)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, PROGRESS_STEPS)
        self.bar.setTextVisible(False)
        self.bar.setMaximumWidth(160)
        self.cancel_button = QPushButton(self.tr("Cancel·la"))
        self.show_button = QPushButton(self.tr("Mostrar a la carpeta"))
        self.show_button.setVisible(False)
        texts = QVBoxLayout()
        texts.addWidget(self.title)
        texts.addWidget(self.status)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addLayout(texts, 1)
        layout.addWidget(self.bar)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.show_button)
        self.set_stage(Stage.QUEUED)

    @property
    def active(self) -> bool:
        return self.stage in ACTIVE_STAGES

    def set_stage(self, stage: Stage, text: str = "") -> None:
        self.stage = stage
        labels = {
            Stage.QUEUED: self.tr("A la cua"),
            Stage.DOWNLOADING: self.tr("Descarregant…"),
            Stage.CONVERTING: self.tr("Convertint…"),
            Stage.DONE: self.tr("Fet"),
            Stage.CANCELLED: self.tr("Cancel·lada"),
            Stage.FAILED: text,
        }
        self.status.setText(labels[stage])
        self.status.setStyleSheet("color: #b22;" if stage is Stage.FAILED else "")
        self.cancel_button.setVisible(self.active)
        self.bar.setVisible(self.active or stage is Stage.DONE)
        self.show_button.setVisible(stage is Stage.DONE)
        if stage in (Stage.QUEUED, Stage.CONVERTING, Stage.DOWNLOADING):
            self.bar.setValue(0)
        elif stage is Stage.DONE:
            self.bar.setValue(PROGRESS_STEPS)

    def set_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setValue(min(PROGRESS_STEPS, round(PROGRESS_STEPS * done / total)))


# --- The window -------------------------------------------------------------------------------------


class YoutubeWindow(QWidget):
    """§1.7 bis: not modal; the main window opens it after the notice (ensure_consent)."""

    def __init__(
        self,
        questions: YoutubeQuestions,
        add_songs: Callable[[Sequence[Path]], None],
        *,
        backend: YoutubeBackend | None = None,
        convert: Converter = convert_to_mp3,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.questions = questions
        self._add_songs = add_songs
        self.backend: YoutubeBackend = backend if backend is not None else YtDlpBackend()
        self._convert = convert
        self.open_url: Callable[[QUrl], object] = QDesktopServices.openUrl
        """[Obre a YouTube] and [Mostrar a la carpeta] (the tests record the address instead)."""
        self._lookups = QThreadPool(self)
        self._lookups.setMaxThreadCount(LOOKUP_THREADS)
        self._downloads = QThreadPool(self)
        self._downloads.setMaxThreadCount(defaults.YOUTUBE_SIMULTANEOUS_DOWNLOADS)
        self._names = threading.Lock()
        self._search_cancel = CancelToken()
        self._generation = 0
        self._query = ""
        self._offset = 0
        self._pending_lookups = 0
        self._thumbnails: dict[str, QPixmap] = {}
        self._withdrawing = False

        self.setWindowTitle(self.tr("Música de YouTube"))
        self.resize(760, 640)
        self.query = QLineEdit()
        self.query.setPlaceholderText(self.tr("Cerca una cançó o enganxa l'enllaç d'un vídeo de YouTube"))
        self.query.setClearButtonEnabled(True)
        self.search_button = QPushButton(self.tr("Cerca"))
        self.withdraw_button = QPushButton(self.tr("Retira la conformitat"))
        self.withdraw_button.setFlat(True)
        self.withdraw_button.setToolTip(
            self.tr(
                "Tanca aquesta finestra i cancel·la les descàrregues; "
                "la propera vegada tornarà a sortir l'avís"
            )
        )
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        self.results = QListWidget()
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.more_button = QPushButton(self.tr("Més resultats"))
        self.more_button.setVisible(False)
        self.add_to_project = QCheckBox(self.tr("Afegeix al projecte en acabar"))
        self.add_to_project.setChecked(True)
        self.download_button = QPushButton(self.tr("Descarrega en MP3"))
        self.download_button.setEnabled(False)
        self.downloads_title = QLabel(self.tr("Descàrregues"))
        self.downloads = QListWidget()
        self.downloads.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._build_layout()

        self.query.returnPressed.connect(self.start_search)
        self.search_button.clicked.connect(self.start_search)
        self.more_button.clicked.connect(self.more_results)
        self.results.itemSelectionChanged.connect(self._refresh_download_button)
        self.download_button.clicked.connect(self.download_selected)
        self.withdraw_button.clicked.connect(self.withdraw_consent)

    def _build_layout(self) -> None:
        top = QHBoxLayout()
        top.addWidget(self.query, 1)
        top.addWidget(self.search_button)
        bottom = QHBoxLayout()
        bottom.addWidget(self.more_button)
        bottom.addStretch(1)
        bottom.addWidget(self.add_to_project)
        bottom.addWidget(self.download_button)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.withdraw_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.message_label)
        layout.addWidget(self.results, 3)
        layout.addLayout(bottom)
        layout.addWidget(self.downloads_title)
        layout.addWidget(self.downloads, 2)
        layout.addLayout(footer)

    # --- State, for the window and the tests ------------------------------------------------------

    @property
    def busy(self) -> bool:
        """A search, a link or a thumbnail is on its way."""
        return self._pending_lookups > 0

    def result_rows(self) -> list[ResultRow]:
        return [self._result_row(self.results.item(i)) for i in range(self.results.count())]

    def download_rows(self) -> list[DownloadRow]:
        rows: list[DownloadRow] = []
        for i in range(self.downloads.count()):
            widget = self.downloads.itemWidget(self.downloads.item(i))
            if isinstance(widget, DownloadRow):
                rows.append(widget)
        return rows

    def active_downloads(self) -> int:
        return sum(1 for row in self.download_rows() if row.active)

    def wait_for_downloads(self, milliseconds: int = CLOSE_WAIT_MS) -> bool:
        return self._downloads.waitForDone(milliseconds)

    def _result_row(self, item: QListWidgetItem) -> ResultRow:
        widget = self.results.itemWidget(item)
        assert isinstance(widget, ResultRow)
        return widget

    def _show_message(self, text: str) -> None:
        self.message_label.setText(text)
        self.message_label.setVisible(bool(text))

    def _token(self) -> ConsentToken | None:
        """The consent, asking again if it was withdrawn meanwhile (from another window)."""
        return ensure_consent(self.questions)

    # --- Searching --------------------------------------------------------------------------------

    def start_search(self) -> None:
        """Retorn or [Cerca]: a pasted link shows its video; anything else is searched."""
        text = self.query.text().strip()
        if not text:
            return
        token = self._token()
        if token is None:
            return
        self._search_cancel.cancel()
        self._search_cancel = cancel = CancelToken()
        self._generation += 1
        generation = self._generation
        self.results.clear()
        self.more_button.setVisible(False)
        self._refresh_download_button()
        self._query = text
        self._offset = 0
        backend = self.backend
        video_id = parse_link(text)
        if video_id is not None:
            self._show_message(self.tr("Cercant…"))
            self._lookup(lambda: (resolve(token, video_id, cancel, backend=backend),), generation, False)
        elif looks_like_link(text):
            self._show_message(message(ERROR_INVALID_LINK))
        else:
            self._show_message(self.tr("Cercant…"))
            self._lookup(
                lambda: search(token, text, defaults.YOUTUBE_RESULTS_PER_PAGE, 0, cancel, backend=backend),
                generation,
                True,
            )

    def more_results(self) -> None:
        """[Més resultats]: the next page of the same search."""
        token = self._token()
        if token is None:
            return
        self._offset += defaults.YOUTUBE_RESULTS_PER_PAGE
        offset, text, cancel, backend = self._offset, self._query, self._search_cancel, self.backend
        self.more_button.setEnabled(False)
        self._lookup(
            lambda: search(token, text, defaults.YOUTUBE_RESULTS_PER_PAGE, offset, cancel, backend=backend),
            self._generation,
            True,
        )

    def _lookup(self, work: Callable[[], object], generation: int, paged: bool) -> None:
        signals = _LookupSignals(self)

        def done(result: object, error: object) -> None:
            self._on_results(signals, generation, paged, result, error)

        signals.done.connect(done)
        self._pending_lookups += 1
        self._lookups.start(_Lookup(work, signals))

    def _on_results(
        self, signals: QObject, generation: int, paged: bool, result: object, error: object
    ) -> None:
        self._pending_lookups -= 1
        signals.deleteLater()
        if generation != self._generation:
            return  # an older search: its answer no longer matters
        self.more_button.setEnabled(True)
        if isinstance(error, CancelledError):
            return
        if isinstance(error, BaseException):
            log_error("cerca", error)
            self._show_message(error_text(error))
            return
        page = [item for item in cast(tuple[object, ...], result) if isinstance(item, SearchResult)]
        for found in page:
            self._add_result(found)
        if self.results.count() == 0:
            self._show_message(self.tr("No s'ha trobat cap resultat."))
        else:
            self._show_message("")
        more = (
            paged
            and len(page) == defaults.YOUTUBE_RESULTS_PER_PAGE
            and self._offset + defaults.YOUTUBE_RESULTS_PER_PAGE < MAX_SEARCH_RESULTS
        )
        self.more_button.setVisible(more)

    def _add_result(self, result: SearchResult) -> None:
        row = ResultRow(result)
        row.open_button.clicked.connect(lambda: self.open_url(QUrl(result.url)))
        item = QListWidgetItem()
        if not row.downloadable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setToolTip(row.reason or "")
        item.setSizeHint(row.sizeHint())
        self.results.addItem(item)
        self.results.setItemWidget(item, row)
        cached = self._thumbnails.get(result.video_id)
        if cached is not None:
            row.set_thumbnail(cached)
        else:
            self._load_thumbnail(result)

    def _load_thumbnail(self, result: SearchResult) -> None:
        token = consent.current()
        if token is None:
            return
        backend, cancel = self.backend, self._search_cancel

        def work() -> QImage:
            image = QImage.fromData(fetch_thumbnail(token, result.thumbnail_url, cancel, backend=backend))
            return image.scaled(
                THUMBNAIL_WIDTH,
                THUMBNAIL_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        signals = _LookupSignals(self)

        def done(image: object, error: object) -> None:
            self._on_thumbnail(signals, result, image, error)

        signals.done.connect(done)
        self._pending_lookups += 1
        self._lookups.start(_Lookup(work, signals))

    def _on_thumbnail(self, signals: QObject, result: SearchResult, image: object, error: object) -> None:
        self._pending_lookups -= 1
        signals.deleteLater()
        if not isinstance(image, QImage) or image.isNull():
            if isinstance(error, BaseException) and not isinstance(error, CancelledError):
                _log.info("YouTube, miniatura de %s: %r", result.video_id, error)
            return
        pixmap = QPixmap.fromImage(image)
        self._thumbnails[result.video_id] = pixmap
        for row in self.result_rows():
            if row.result.video_id == result.video_id:
                row.set_thumbnail(pixmap)

    # --- Downloading ------------------------------------------------------------------------------

    def selected_results(self) -> list[SearchResult]:
        rows = [self._result_row(item) for item in self.results.selectedItems()]
        order = {id(row): i for i, row in enumerate(self.result_rows())}
        rows.sort(key=lambda row: order.get(id(row), 0))
        return [row.result for row in rows if row.downloadable]

    def _refresh_download_button(self) -> None:
        self.download_button.setEnabled(bool(self.selected_results()))

    def suggested_folder(self) -> Path:
        """The folder of the last download, or Documents the first time (§1.7 bis)."""
        saved = user_settings().value(LAST_FOLDER_KEY, "")
        if isinstance(saved, str) and saved and Path(saved).is_dir():
            return Path(saved)
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        return Path(documents) if documents else Path.home()

    def download_selected(self) -> None:
        """[Descarrega en MP3]: one folder for the whole selection, then the queue."""
        chosen = self.selected_results()
        if not chosen:
            return
        token = self._token()
        if token is None:
            return
        folder = self.questions.choose_download_folder(self.suggested_folder())
        if folder is None:
            return
        user_settings().setValue(LAST_FOLDER_KEY, str(folder))
        for result in chosen:
            self._enqueue(DownloadJob(result, folder, token, self.backend, self._convert, self._names))
        self.results.clearSelection()

    def _enqueue(self, job: DownloadJob) -> None:
        row = DownloadRow(job)
        item = QListWidgetItem()
        item.setSizeHint(row.sizeHint())
        self.downloads.addItem(item)
        self.downloads.setItemWidget(item, row)
        row.cancel_button.clicked.connect(lambda: self.cancel_download(row))
        row.show_button.clicked.connect(lambda: self._show_in_folder(row))
        signals = _DownloadSignals(self)

        def progress(stage: object, done: int, total: int) -> None:
            self._on_download_progress(row, stage, done, total)

        def finished(path: object, error: object) -> None:
            self._on_download_finished(signals, row, path, error)

        signals.progress.connect(progress)
        signals.finished.connect(finished)
        self._downloads.start(_Download(job, signals))

    def cancel_download(self, row: DownloadRow) -> None:
        if not row.active:
            return
        row.job.cancel.cancel()
        if row.stage is Stage.QUEUED:
            row.set_stage(Stage.CANCELLED)  # it will not start; its signal is ignored

    def cancel_all(self) -> None:
        self._search_cancel.cancel()
        for row in self.download_rows():
            self.cancel_download(row)

    def _on_download_progress(self, row: DownloadRow, stage: object, done: int, total: int) -> None:
        if not row.active or row.job.cancel.cancelled or not isinstance(stage, Stage):
            return
        if row.stage is not stage:
            row.set_stage(stage)
        row.set_progress(done, total)

    def _on_download_finished(self, signals: QObject, row: DownloadRow, path: object, error: object) -> None:
        signals.deleteLater()
        if isinstance(path, Path):
            row.path = path
            row.set_stage(Stage.DONE)
            if self.add_to_project.isChecked() and not self._withdrawing:
                self._add_songs([path])
        elif isinstance(error, CancelledError):
            row.set_stage(Stage.CANCELLED)
        elif isinstance(error, BaseException):
            log_error(f"descàrrega de {row.job.result.video_id}", error)
            row.set_stage(Stage.FAILED, error_text(error))

    def _show_in_folder(self, row: DownloadRow) -> None:
        if row.path is not None:
            self.open_url(QUrl.fromLocalFile(str(row.path.parent)))

    # --- Closing ----------------------------------------------------------------------------------

    def withdraw_consent(self) -> None:
        """ "Retira la conformitat": cancels everything, closes, and the notice comes back next time."""
        self._withdrawing = True
        try:
            consent.revoke()
            self.cancel_all()
            self.wait_for_downloads()
            self._generation += 1  # the answers still on their way are dropped
            self.results.clear()
            self.more_button.setVisible(False)
            self._show_message("")
            self.close()
        finally:
            self._withdrawing = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt)
        """With downloads in progress, asks; if confirmed, cancels them and leaves no half files."""
        active = self.active_downloads()
        if active and not self._withdrawing and not self.questions.confirm_cancel_downloads(active):
            event.ignore()
            return
        self.cancel_all()
        if active:
            self.wait_for_downloads()
        super().closeEvent(event)
