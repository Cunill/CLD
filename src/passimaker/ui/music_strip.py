"""The music strip under the storyboard (§1.0 and §1.7).

The songs, in order, with their name, their real duration (after the trim) and the fade marks.
They are added with [+ Música] or by dropping audio files, removed with Supr or the context menu,
and reordered by dragging. Like the storyboard, the strip is a read-only view of the project:
every edit becomes a command for the controller (rule 2).

Reading the duration of a song asks FFmpeg (tens of milliseconds per file), so new songs are read
in a worker thread (rule 6) by ``SongLoader``.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import (
    QAbstractListModel,
    QMimeData,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QWidget,
)

from passimaker.common import PassiMakerError
from passimaker.ffmpeg import probe
from passimaker.model import Change, ProjectController, Song
from passimaker.model.commands import AddSongs, MoveSongs, RemoveSongs, SetMusicSettings
from passimaker.model.editing import song_duration
from passimaker.ui.formatting import clock

AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus"})
"""§1.7: MP3, WAV, M4A/AAC, FLAC, OGG, WMA and OPUS."""

SONG_MIME = "application/x-passimaker-songs"
"""Internal drag: the ids of the songs being moved, one per line."""

FADE_IN_MARK = "◢"
FADE_OUT_MARK = "◣"
"""The fade marks of §1.0 ("Cançó A 3:12 ◢◣"): symbols, not words."""

MISSING_COLOUR = QColor(200, 40, 40)
"""§1.7: a song that cannot be played is marked in red."""

STRIP_HEIGHT = 40
ADD_BUTTON_WIDTH = 36
NO_AUDIO_KEY = "ffmpeg.no_audio"

type AnyIndex = QModelIndex | QPersistentModelIndex

_NO_PARENT = QModelIndex()
_ids = itertools.count(1)
"""Song ids are only unique inside a project; the controller renames a repeated one."""


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def song_label(number: int, song: Song) -> str:
    """ "1. Cançó A  3:12 ◢◣": the number, the file name, the duration and the fades."""
    marks = (FADE_IN_MARK if song.fade_in.enabled else "") + (FADE_OUT_MARK if song.fade_out.enabled else "")
    text = f"{number}. {song.path.stem}  {clock(song_duration(song))}"
    return f"{text} {marks}" if marks else text


# --- Reading new songs ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FailedSong:
    path: Path
    message_key: str
    """Key of passimaker.i18n with the reason (unreadable, no sound...)."""


@dataclass(frozen=True, slots=True)
class LoadedSongs:
    songs: tuple[Song, ...]
    failures: tuple[FailedSong, ...]
    index: int | None


def read_song(path: Path) -> Song | FailedSong:
    """A new song with the default settings of §1.7, or why it cannot be used."""
    try:
        info = probe(path)
    except PassiMakerError as error:
        return FailedSong(path, error.message_key)
    if not info.has_audio or info.duration_s <= 0:
        return FailedSong(path, NO_AUDIO_KEY)
    return Song(
        id=f"s{next(_ids):05d}",
        path=Path(path).absolute(),
        relative_path=None,
        original_duration_s=info.duration_s,
    )


class _Signals(QObject):
    done = Signal(object)


class _Read(QRunnable):
    def __init__(self, paths: Sequence[Path], index: int | None, signals: _Signals) -> None:
        super().__init__()
        self._paths = tuple(paths)
        self._index = index
        self._signals = signals

    def run(self) -> None:
        songs: list[Song] = []
        failures: list[FailedSong] = []
        for path in self._paths:
            result = read_song(path)
            if isinstance(result, Song):
                songs.append(result)
            else:
                failures.append(result)
        self._signals.done.emit(LoadedSongs(tuple(songs), tuple(failures), self._index))


class SongQuestions(Protocol):
    def report_song_failures(self, failures: Sequence[FailedSong]) -> None:
        """ "N cançons no s'han pogut afegir", with the reason of each one."""
        ...


class SongLoader(QObject):
    """Reads the duration of new songs in a worker thread and adds them with AddSongs."""

    finished = Signal(int)
    """How many songs were added."""

    def __init__(
        self, controller: ProjectController, questions: SongQuestions, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._questions = questions
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._pending = 0

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def start(self, paths: Sequence[Path], index: int | None = None) -> None:
        """Adds these audio files at index (None = at the end); other files are ignored."""
        audio = [path for path in paths if is_audio(path)]
        if not audio:
            return
        self._pending += 1
        signals = _Signals(self)
        signals.done.connect(self._on_done)
        self._pool.start(_Read(audio, index, signals))

    def wait(self, milliseconds: int = 30_000) -> bool:
        return self._pool.waitForDone(milliseconds)

    def _on_done(self, result: object) -> None:
        self._pending -= 1
        if not isinstance(result, LoadedSongs):
            return
        if result.songs:
            self._controller.execute(AddSongs(result.songs, result.index))
        if result.failures:
            self._questions.report_song_failures(result.failures)
        self.finished.emit(len(result.songs))


# --- The strip ------------------------------------------------------------------------------------


class SongRole(IntEnum):
    SONG_ID = int(Qt.ItemDataRole.UserRole)
    SONG = int(Qt.ItemDataRole.UserRole) + 1
    MISSING = int(Qt.ItemDataRole.UserRole) + 2


class SongListModel(QAbstractListModel):
    """Songs of the project, in order; drags and drops become commands."""

    files_dropped = Signal(list, int)
    """Paths dropped on the strip and the position they were dropped at (-1 = at the end)."""

    def __init__(self, controller: ProjectController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._songs: tuple[Song, ...] = controller.project.music.songs
        self._missing: frozenset[str] = frozenset()
        self._unsubscribe = controller.subscribe(self._on_changes)

    def songs(self) -> tuple[Song, ...]:
        return self._songs

    def song_at(self, row: int) -> Song | None:
        return self._songs[row] if 0 <= row < len(self._songs) else None

    def set_missing(self, song_ids: frozenset[str]) -> None:
        """Songs whose file was not found: drawn in red (§1.7)."""
        if song_ids != self._missing:
            self._missing = song_ids
            if self._songs:
                self.dataChanged.emit(self.index(0, 0), self.index(len(self._songs) - 1, 0))

    def rowCount(self, parent: AnyIndex = _NO_PARENT) -> int:  # noqa: N802 (Qt)
        return 0 if parent.isValid() else len(self._songs)

    def data(self, index: AnyIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        song = self.song_at(index.row()) if index.isValid() else None
        if song is None:
            return None
        missing = song.id in self._missing
        if role == Qt.ItemDataRole.DisplayRole:
            return song_label(index.row() + 1, song)
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(song.path)
        if role == Qt.ItemDataRole.ForegroundRole and missing:
            return QBrush(MISSING_COLOUR)
        if role == SongRole.SONG_ID:
            return song.id
        if role == SongRole.SONG:
            return song
        if role == SongRole.MISSING:
            return missing
        return None

    def flags(self, index: AnyIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDropEnabled
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802 (Qt)
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:  # noqa: N802 (Qt)
        return [SONG_MIME, "text/uri-list"]

    def mimeData(self, indexes: Sequence[AnyIndex]) -> QMimeData:  # noqa: N802 (Qt)
        ids = [self._songs[i.row()].id for i in indexes if i.isValid()]
        data = QMimeData()
        data.setData(SONG_MIME, "\n".join(ids).encode("utf-8"))
        return data

    def canDropMimeData(  # noqa: N802 (Qt)
        self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: AnyIndex
    ) -> bool:
        return data.hasFormat(SONG_MIME) or data.hasUrls()

    def dropMimeData(  # noqa: N802 (Qt)
        self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: AnyIndex
    ) -> bool:
        if action == Qt.DropAction.IgnoreAction:
            return True
        target = row if row >= 0 else (parent.row() if parent.isValid() else len(self._songs))
        if data.hasFormat(SONG_MIME):
            self.move(data.data(SONG_MIME).toStdString().split("\n"), target)
            return False
            # False: the view must not remove the dragged rows itself (the controller already did).
        if data.hasUrls():
            paths = [Path(url.toLocalFile()) for url in data.urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths, target)
            return bool(paths)
        return False

    def move(self, song_ids: Sequence[str], target: int) -> None:
        known = {s.id for s in self._songs}
        moving = tuple(sid for sid in song_ids if sid in known)
        if moving:
            self._controller.execute(MoveSongs(moving, target))

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if Change.MUSIC not in changes:
            return
        songs = self._controller.project.music.songs
        if songs and [s.id for s in songs] == [s.id for s in self._songs]:
            # Same songs in the same order (a trim, a fade, a volume): the selection stays.
            self._songs = songs
            self.dataChanged.emit(self.index(0, 0), self.index(len(songs) - 1, 0))
            return
        self.beginResetModel()
        self._songs = songs
        self.endResetModel()

    def close(self) -> None:
        self._unsubscribe()


class SongListView(QListView):
    """The songs in one row, reordered by dragging."""

    def __init__(self, model: SongListModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModel(model)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setSpacing(4)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(STRIP_HEIGHT)

    def selected_ids(self) -> tuple[str, ...]:
        rows = sorted(index.row() for index in self.selectionModel().selectedIndexes())
        model = self.model()
        if not isinstance(model, SongListModel):
            return ()
        songs = [model.song_at(row) for row in rows]
        return tuple(song.id for song in songs if song is not None)


class MusicStrip(QWidget):
    """ "MÚSICA: [1. Cançó A 3:12 ◢◣] [2. Cançó B 2:40 ◢◣] [+]" and "Mantenir ajustat" (§1.0, §1.7)."""

    add_requested = Signal()
    files_dropped = Signal(list, int)

    def __init__(self, controller: ProjectController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.model = SongListModel(controller, self)
        self.view = SongListView(self.model)
        self.title = QLabel(self.tr("Música:"))
        self.empty_label = QLabel(self.tr("Sense música. Afegeix-ne amb [+] o arrossega els fitxers aquí."))
        self.add_button = QPushButton(self.tr("+"))
        self.add_button.setToolTip(self.tr("Afegir música"))
        self.add_button.setFixedWidth(ADD_BUTTON_WIDTH)
        self.add_button.clicked.connect(self.add_requested)
        self.keep_fitted = QCheckBox(self.tr("Mantenir ajustat"))
        self.keep_fitted.setToolTip(
            self.tr("Torna a ajustar les durades a la música cada vegada que s'afegeixen fotos o cançons")
        )
        self.keep_fitted.toggled.connect(self._on_keep_fitted)

        self.remove_action = QAction(self.tr("Eliminar la cançó"), self)
        self.remove_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.remove_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.remove_action.triggered.connect(self.remove_selected)
        self.view.addAction(self.remove_action)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(self.title)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.empty_label, 1)
        layout.addWidget(self.add_button)
        layout.addWidget(self.keep_fitted)

        self.model.files_dropped.connect(self.files_dropped)
        self.model.modelReset.connect(self.refresh)
        self._unsubscribe = controller.subscribe(self._on_changes)
        self.refresh()

    def remove_selected(self) -> None:
        ids = self.view.selected_ids()
        if ids:
            self._controller.execute(RemoveSongs(frozenset(ids)))

    def refresh(self) -> None:
        has_songs = self.model.rowCount() > 0
        self.view.setVisible(has_songs)
        self.empty_label.setVisible(not has_songs)
        self.remove_action.setEnabled(has_songs)
        keep = self._controller.project.music.keep_fitted
        if self.keep_fitted.isChecked() != keep:
            self.keep_fitted.blockSignals(True)
            self.keep_fitted.setChecked(keep)
            self.keep_fitted.blockSignals(False)

    def _on_keep_fitted(self, checked: bool) -> None:
        if checked != self._controller.project.music.keep_fitted:
            self._controller.execute(SetMusicSettings(keep_fitted=checked))

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if Change.MUSIC in changes:
            self.refresh()

    def close_strip(self) -> None:
        self._unsubscribe()
        self.model.close()
