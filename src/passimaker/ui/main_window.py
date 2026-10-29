"""Main window: toolbar, preview area, properties, storyboard and status bar (§1.0).

The window owns the controller and is the only place that turns a gesture into a command. The
music strip, the export dialog and the project files (block B11) live in their own modules; this
one only builds them, connects them and puts their actions in the menus. The real preview is
block B13's.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from passimaker.images import ImageSource
from passimaker.logs import log_dir
from passimaker.model import Change, OutputFormat, ProjectController
from passimaker.model.commands import (
    DuplicatePhotos,
    FitToMusic,
    MovePhotos,
    RemovePhotos,
    RerollMotions,
    RotatePhotos,
    SetPhotoMotion,
    SetProjectSettings,
    SortPhotos,
)
from passimaker.model.types import MotionMode, Rotation
from passimaker.recorder import CaptureBackend
from passimaker.ui.delegate import ThumbnailSize
from passimaker.ui.dialogs import DialogQuestions, WindowQuestions
from passimaker.ui.drops import sort_dropped
from passimaker.ui.duration_status import DurationStatus, fit_problem
from passimaker.ui.export_dialog import VideoExport
from passimaker.ui.formatting import clock
from passimaker.ui.help import HelpWindows
from passimaker.ui.importing import PhotoImporter
from passimaker.ui.music_strip import MusicStrip, SongLoader
from passimaker.ui.photo_panel import PhotoPanel
from passimaker.ui.photos import PhotoListModel
from passimaker.ui.player_panel import PlayerPanel
from passimaker.ui.project_files import MissingFilesBar, ProjectFiles, RecentProjects
from passimaker.ui.project_panel import ProjectPanel
from passimaker.ui.properties import PropertiesPanel
from passimaker.ui.record_dialog import RecordDialogs, RecordQuestions, RecordWindow
from passimaker.ui.song_panel import SongPanel
from passimaker.ui.storyboard import StoryboardPanel
from passimaker.ui.thumbnails import ThumbnailBridge, ThumbnailProvider
from passimaker.ui.youtube_dialog import YoutubeDialogs, YoutubeQuestions, YoutubeWindow, ensure_consent
from passimaker.youtube import YoutubeBackend

CONFIRM_DELETE_FROM = 5
"""§1.2 and decision 0007: a confirmation from five photos on, even though undo exists."""

WINDOW_SIZE = QSize(1280, 800)
TOOLBAR_ICON = QSize(20, 20)


class MainWindow(QMainWindow):
    """Photos (B10), music, export and project files (B11), photo and song controls (B14)."""

    music_changed = Signal()
    """The songs or the music settings of the project changed (for the player of B13/B14)."""

    def __init__(
        self,
        controller: ProjectController,
        thumbnails: ThumbnailProvider,
        images: ImageSource,
        questions: WindowQuestions | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._service = thumbnails
        self.questions: WindowQuestions = questions if questions is not None else DialogQuestions(self)
        self.thumbnails = ThumbnailBridge(thumbnails, self)
        self.model = PhotoListModel(controller, self)
        self.importer = PhotoImporter(controller, self.questions, self)
        self.songs = SongLoader(controller, self.questions, self)
        self.files = ProjectFiles(controller, self.questions, parent=self)
        self.video_export = VideoExport(self.questions, self)
        self.help = HelpWindows(self, log_dir())
        self.youtube_questions: YoutubeQuestions = YoutubeDialogs(self)
        self.youtube_backend: YoutubeBackend | None = None
        """None: the real one (yt-dlp); the tests put tests/fakes/youtube.py here before opening."""
        self.youtube_window: YoutubeWindow | None = None
        self.record_questions: RecordQuestions = RecordDialogs(self)
        self.record_backend: CaptureBackend | None = None
        """None: the real one (soundcard); the tests put tests/fakes/recorder.py here before opening."""
        self.record_window: RecordWindow | None = None

        self.setWindowTitle(self.tr("PassiMaker"))
        self.resize(WINDOW_SIZE)
        self.setAcceptDrops(True)

        self.player_panel = PlayerPanel(controller, images, thumbnails.get_intermediate)
        self.panel = ProjectPanel(controller)
        self.photo_panel = PhotoPanel(controller)
        self.song_panel = SongPanel(controller)
        self.properties = PropertiesPanel(self.panel, self.photo_panel, self.song_panel)
        self.storyboard = StoryboardPanel(self.model, self.thumbnails)
        self.view = self.storyboard.view
        self.music_strip = MusicStrip(controller)
        self.recent_projects = RecentProjects(self.files)
        self._preview_playing = False
        self._build_layout()
        self._add_music_strip()
        self._build_actions()
        self._build_status_bar()
        self._connect()
        self.refresh_status()
        self._refresh_actions()
        self._refresh_title()

    # --- Layout ----------------------------------------------------------------------------------

    def _build_layout(self) -> None:
        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(self.player_panel)
        left.addWidget(self.properties)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 2)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.storyboard)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.setCentralWidget(self.splitter)

    def _add_music_strip(self) -> None:
        """§1.0: the music strip goes under the main splitter, across the whole window."""
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.takeCentralWidget(), 1)
        layout.addWidget(self.music_strip)
        self.setCentralWidget(central)
        empty = self.storyboard.empty.layout()
        if empty is not None:
            empty.addWidget(self.recent_projects)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self.status_label = QLabel()
        bar.addWidget(self.status_label)
        self.duration_status = DurationStatus()
        self.duration_status.fit_requested.connect(self.fit_to_music)
        bar.addWidget(self.duration_status)
        self.missing_bar = MissingFilesBar(self.files)
        bar.addWidget(self.missing_bar)
        self.audio_warning = QLabel()
        self.audio_warning.setVisible(False)
        bar.addWidget(self.audio_warning)
        self.progress_widget = QWidget()
        progress_layout = QHBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(180)
        self.cancel_button = QPushButton(self.tr("Cancel·lar"))
        self.cancel_button.clicked.connect(self.importer.cancel)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.cancel_button)
        self.progress_widget.setVisible(False)
        bar.addPermanentWidget(self.progress_widget)

    # --- Actions ---------------------------------------------------------------------------------

    def _build_actions(self) -> None:
        self.add_photos_action = QAction(self.tr("+ Fotos"), self)
        self.add_photos_action.setToolTip(
            self.tr("Afegeix fotos al passi (també les pots arrossegar a la finestra)")
        )
        self.add_photos_action.triggered.connect(self.choose_photos)
        self.add_folder_action = QAction(self.tr("Afegir una carpeta…"), self)
        self.add_folder_action.triggered.connect(self.choose_folder)
        self.add_music_action = QAction(self.tr("+ Música"), self)
        self.add_music_action.setToolTip(
            self.tr("Afegeix cançons (també les pots arrossegar a la franja de música)")
        )
        self.add_music_action.triggered.connect(self.choose_music)
        self.music_menu = QMenu(self.tr("+ Música"), self)
        self.add_music_action.setMenu(self.music_menu)
        self.music_files_action = self._add_music_source(self.tr("Des de fitxers…"), self.choose_music)
        self.music_youtube_action = self._add_music_source(self.tr("Des de YouTube…"), self.open_youtube)
        self.music_record_action = self._add_music_source(self.tr("Grava el que sona…"), self.open_recorder)
        self.fit_to_music_action = QAction(self.tr("Ajustar a la música"), self)
        self.fit_to_music_action.setToolTip(
            self.tr("Canvia la durada de les fotos perquè el passi acabi alhora que la música")
        )
        self.fit_to_music_action.triggered.connect(self.fit_to_music)
        self.export_action = QAction(self.tr("Exportar vídeo"), self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setToolTip(self.tr("Desa el passi com a vídeo MP4 (Ctrl+E)"))
        self.export_action.triggered.connect(self.export_video)

        self.open_action = QAction(self.tr("Obrir…"), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_project)
        self.save_action = QAction(self.tr("Desar"), self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_project)
        self.save_as_action = QAction(self.tr("Desar com a…"), self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.triggered.connect(self.save_project_as)
        self.find_missing_action = QAction(self.tr("Cercar els fitxers que no es troben…"), self)
        self.find_missing_action.triggered.connect(lambda: self.files.find_missing())
        self.recent_menu = QMenu(self.tr("Projectes recents"), self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.quit_action = QAction(self.tr("Sortir"), self)
        self.quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.quit_action.triggered.connect(self.close)

        self.undo_action = QAction(self.tr("Desfer"), self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setToolTip(self.tr("Desfà l'últim canvi (Ctrl+Z)"))
        self.redo_action = QAction(self.tr("Refer"), self)
        self.redo_action.setShortcuts([QKeySequence(QKeySequence.StandardKey.Redo), QKeySequence("Ctrl+Y")])
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setToolTip(self.tr("Torna a fer el canvi desfet (Ctrl+Y)"))

        self.delete_action = QAction(self.tr("Eliminar"), self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self.delete_selected)
        self.duplicate_action = QAction(self.tr("Duplicar"), self)
        self.duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        self.duplicate_action.triggered.connect(self.duplicate_selected)
        self.select_all_action = QAction(self.tr("Seleccionar-ho tot"), self)
        self.select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.select_all_action.triggered.connect(self.view.selectAll)
        self.move_left_action = QAction(self.tr("Moure a l'esquerra"), self)
        self.move_left_action.setShortcut(QKeySequence("Ctrl+Left"))
        self.move_left_action.triggered.connect(lambda: self.move_selected(-1))
        self.move_right_action = QAction(self.tr("Moure a la dreta"), self)
        self.move_right_action.setShortcut(QKeySequence("Ctrl+Right"))
        self.move_right_action.triggered.connect(lambda: self.move_selected(1))
        self.rotate_right_action = QAction(self.tr("Girar a la dreta"), self)
        self.rotate_right_action.setShortcut(QKeySequence("Ctrl+R"))
        self.rotate_right_action.triggered.connect(lambda: self.rotate_selected(Rotation.R90))
        self.rotate_left_action = QAction(self.tr("Girar a l'esquerra"), self)
        self.rotate_left_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.rotate_left_action.triggered.connect(lambda: self.rotate_selected(Rotation.R270))
        self.reroll_action = QAction(self.tr("Nou moviment a l'atzar"), self)
        self.reroll_action.triggered.connect(self.reroll_selected)
        self.reroll_all_action = QAction(self.tr("Tornar a sortejar tots"), self)
        self.reroll_all_action.triggered.connect(self.reroll_all)
        self.reset_motions_action = QAction(self.tr("Restablir tots a automàtic"), self)
        self.reset_motions_action.triggered.connect(self.reset_motions)
        self.sort_by_date_action = QAction(self.tr("Ordenar per data"), self)
        self.sort_by_date_action.triggered.connect(lambda: self.controller.execute(SortPhotos(True)))
        self.sort_by_name_action = QAction(self.tr("Ordenar per nom"), self)
        self.sort_by_name_action.triggered.connect(lambda: self.controller.execute(SortPhotos(False)))

        self.format_action = QAction(self.tr("Format vertical"), self)
        self.format_action.setCheckable(True)
        self.format_action.toggled.connect(self._on_format_toggled)
        self.format_action.setToolTip(self.tr("Vídeo vertical 9:16, per veure'l al mòbil"))

        self.guide_action = QAction(self.tr("Guia d'ús"), self)
        self.guide_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        self.guide_action.triggered.connect(self.help.show_guide)
        self.about_action = QAction(self.tr("Quant a PassiMaker"), self)
        self.about_action.triggered.connect(self.help.show_about)

        self.size_actions = self._build_size_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_context_menu()

    def _add_music_source(self, text: str, slot: Callable[[], None]) -> QAction:
        """One entry of the [+ Música ▾] menu (also in the music strip's [+] and the File menu)."""
        action = self.music_menu.addAction(text)
        action.triggered.connect(slot)
        return action

    def _build_size_actions(self) -> dict[ThumbnailSize, QAction]:
        group = QActionGroup(self)
        labels = {
            ThumbnailSize.SMALL: self.tr("Petites"),
            ThumbnailSize.MEDIUM: self.tr("Mitjanes"),
            ThumbnailSize.LARGE: self.tr("Grans"),
        }
        actions: dict[ThumbnailSize, QAction] = {}
        for size, label in labels.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(size is self.view.thumbnail_size)
            action.triggered.connect(lambda _checked=False, s=size: self.set_thumbnail_size(s))
            group.addAction(action)
            actions[size] = action
        return actions

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu(self.tr("Fitxer"))
        file_menu.addAction(self.open_action)
        file_menu.addMenu(self.recent_menu)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.add_photos_action)
        file_menu.addAction(self.add_folder_action)
        file_menu.addAction(self.add_music_action)
        file_menu.addAction(self.fit_to_music_action)
        file_menu.addAction(self.find_missing_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)
        edit_menu = bar.addMenu(self.tr("Edita"))
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.select_all_action)
        edit_menu.addAction(self.duplicate_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.move_left_action)
        edit_menu.addAction(self.move_right_action)
        edit_menu.addAction(self.rotate_left_action)
        edit_menu.addAction(self.rotate_right_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.reroll_action)
        edit_menu.addAction(self.reroll_all_action)
        edit_menu.addAction(self.reset_motions_action)
        view_menu = bar.addMenu(self.tr("Visualitza"))
        view_menu.addAction(self.sort_by_date_action)
        view_menu.addAction(self.sort_by_name_action)
        size_menu = view_menu.addMenu(self.tr("Mida de les miniatures"))
        for action in self.size_actions.values():
            size_menu.addAction(action)
        self.help_menu = bar.addMenu(self.tr("Ajuda"))
        self.help_menu.addAction(self.guide_action)
        self.help_menu.addSeparator()
        self.help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar(self.tr("Principal"), self)
        self.toolbar.setIconSize(TOOLBAR_ICON)
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self.toolbar.addAction(self.add_photos_action)
        self.toolbar.addAction(self.add_music_action)
        music_button = self.toolbar.widgetForAction(self.add_music_action)
        if isinstance(music_button, QToolButton):
            music_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addAction(self.fit_to_music_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.undo_action)
        self.toolbar.addAction(self.redo_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.format_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.export_action)

    def _build_context_menu(self) -> None:
        """The photo actions belong to the storyboard: in the context menu and, above all, with
        their shortcut limited to it, so that Supr or Ctrl+A inside a number box edit the number
        instead of the photos."""
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        for action in (
            self.duplicate_action,
            self.delete_action,
            self.rotate_left_action,
            self.rotate_right_action,
            self.reroll_action,
            self.move_left_action,
            self.move_right_action,
            self.select_all_action,
        ):
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.view.addAction(action)

    def _connect(self) -> None:
        self.storyboard.choose_photos.connect(self.choose_photos)
        self.view.files_dropped.connect(self._on_files_dropped)
        self.model.modelReset.connect(self._on_model_reset)
        self.controller.subscribe(self._on_changes)
        self.view.selectionModel().selectionChanged.connect(self._on_selection)
        self.importer.started.connect(self._on_import_started)
        self.importer.progress.connect(self._on_import_progress)
        self.importer.finished.connect(self._on_import_finished)
        self.music_strip.add_button.setMenu(self.music_menu)
        self.music_strip.files_dropped.connect(self._on_files_dropped_on_music)
        self.files.state_changed.connect(self._refresh_title)
        self.files.missing_changed.connect(self._on_missing_changed)
        self.recent_projects.open_requested.connect(self.open_path)
        self.video_export.finished.connect(self._on_export_finished)
        self.music_changed.connect(lambda: self.player_panel.reload_audio(only_if_changed=True))
        self.photo_panel.rotate_requested.connect(self.rotate_selected)
        self.music_strip.view.selectionModel().selectionChanged.connect(self._on_song_selection)
        self.music_strip.model.modelReset.connect(self._on_song_selection)
        self.song_panel.listening_started.connect(self.player_panel.player.pause)
        self.player_panel.player.state_changed.connect(self._on_player_state)
        self.player_panel.audio_problem.connect(self._on_audio_problem)

    # --- Commands --------------------------------------------------------------------------------

    def choose_photos(self) -> None:
        paths = self.questions.choose_photos()
        if paths:
            self.import_paths(paths)

    def choose_folder(self) -> None:
        folder = self.questions.choose_folder()
        if folder is not None:
            self.import_paths([folder])

    def import_paths(self, paths: Sequence[Path], index: int | None = None) -> None:
        self.importer.start(paths, index)

    def choose_music(self) -> None:
        paths = self.questions.choose_music()
        if paths:
            self.add_songs(paths)

    def add_songs(self, paths: Sequence[Path], index: int | None = None) -> None:
        self.songs.start(paths, index)

    def open_youtube(self) -> None:
        """§1.7 bis: the notice first (once per run of the program), then the window, not modal."""
        if ensure_consent(self.youtube_questions) is None:
            return
        if self.youtube_window is None:
            self.youtube_window = YoutubeWindow(
                self.youtube_questions, self.add_songs, backend=self.youtube_backend, parent=self
            )
        self.youtube_window.show()
        self.youtube_window.raise_()
        self.youtube_window.activateWindow()

    def open_recorder(self) -> None:
        """§1.7 ter: the window "Grava el que sona", not modal and without any notice (G2)."""
        if self.record_window is None:
            self.record_window = RecordWindow(
                self.record_questions, self.add_songs, backend=self.record_backend, parent=self
            )
        self.record_window.show()
        self.record_window.raise_()
        self.record_window.activateWindow()

    def fit_to_music(self) -> None:
        """§1.7: asks first when the photos would end outside 1-24 s."""
        project = self.controller.project
        if not project.photos or not project.music.songs:
            return
        check = fit_problem(project)
        if check is not None and not self.questions.confirm_fit(check):
            return
        self.controller.execute(FitToMusic())

    def export_video(self) -> None:
        self.video_export.start(self.controller.project, self.files.display_name())
        self._refresh_actions()

    def open_project(self) -> None:
        self.files.open()

    def open_path(self, path: Path) -> None:
        self.files.open_path(path)

    def save_project(self) -> None:
        self.files.save()

    def save_project_as(self) -> None:
        self.files.save_as()

    def delete_selected(self) -> None:
        ids = self.view.selected_ids()
        if not ids:
            return
        if len(ids) >= CONFIRM_DELETE_FROM and not self.questions.confirm_delete(len(ids)):
            return
        self.thumbnails.forget(frozenset(ids))
        self.controller.execute(RemovePhotos(frozenset(ids)))

    def duplicate_selected(self) -> None:
        ids = self.view.selected_ids()
        if ids:
            self.controller.execute(DuplicatePhotos(ids))

    def move_selected(self, direction: int) -> None:
        """Ctrl+Left and Ctrl+Right move the selected photos one place (§1.2)."""
        rows = self.view.selected_rows()
        if not rows:
            return
        target = rows[0] - 1 if direction < 0 else rows[-1] + 2
        if target < 0 or target > len(self.model.photos()):
            return
        ids = self.view.selected_ids()
        self.controller.execute(MovePhotos(ids, target))
        self.view.select_ids(ids)

    def rotate_selected(self, rotation: Rotation) -> None:
        ids = self.view.selected_ids()
        if not ids:
            return
        self.thumbnails.forget(frozenset(ids))
        self.controller.execute(RotatePhotos(frozenset(ids), rotation))
        self.view.request_visible_thumbnails()

    def reroll_selected(self) -> None:
        ids = self.view.selected_ids()
        if ids:
            self.controller.execute(RerollMotions(frozenset(ids)))

    def reroll_all(self) -> None:
        """§1.5: a new motion for every photo in automatic mode; the manual ones stay."""
        if self.controller.project.photos:
            self.controller.execute(RerollMotions(None))

    def reset_motions(self) -> None:
        """§1.5, "Restablir tots a automàtic": the photos with a fixed motion get a drawn one."""
        manual = frozenset(p.id for p in self.controller.project.photos if p.motion.mode is MotionMode.MANUAL)
        if manual:
            self.controller.execute(SetPhotoMotion(manual, None))

    def undo(self) -> None:
        self.controller.undo()

    def redo(self) -> None:
        self.controller.redo()

    def set_thumbnail_size(self, size: ThumbnailSize) -> None:
        self.view.set_thumbnail_size(size)
        self.size_actions[size].setChecked(True)
        self.view.schedule_thumbnails()

    # --- Reactions -------------------------------------------------------------------------------

    def _on_format_toggled(self, vertical: bool) -> None:
        wanted = OutputFormat.VERTICAL if vertical else OutputFormat.HORIZONTAL
        if wanted is not self.controller.project.output_format:
            self.controller.execute(SetProjectSettings(output_format=wanted))

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if changes - {Change.SAVED_STATE}:
            self.refresh_status()
        if Change.MUSIC in changes:
            self.music_changed.emit()
        self.properties.refresh_tabs()
        self._refresh_actions()
        vertical = self.controller.project.output_format is OutputFormat.VERTICAL
        if self.format_action.isChecked() != vertical:
            self.format_action.blockSignals(True)
            self.format_action.setChecked(vertical)
            self.format_action.blockSignals(False)

    def _on_model_reset(self) -> None:
        self.storyboard.update_state()
        self.view.schedule_thumbnails()
        self._on_selection()

    def _on_selection(self) -> None:
        photo = self.view.current_photo()
        rows = self.view.selected_rows()
        if photo is None and rows:
            photo = self.model.photo_at(rows[0])
        self.player_panel.show_photo(photo.id if photo is not None else None)
        self.properties.show_photos(self.view.selected_ids())
        self._refresh_actions()

    def _on_song_selection(self) -> None:
        ids = self.music_strip.view.selected_ids()
        self.properties.show_song(ids[0] if ids else None)

    def _on_player_state(self, playing: bool, _t: float, _photo_index: int) -> None:
        """The preview and [Escoltar el tros] do not sound at the same time.

        Only the moment the preview starts stops the listening: reports of "playing" that were
        already on their way when the listening paused the preview must not stop it.
        """
        started = playing and not self._preview_playing
        self._preview_playing = playing
        if started:
            self.song_panel.listening.stop()

    def _on_audio_problem(self, text: str) -> None:
        """B13/B14 note: the preview could not prepare the music, so it plays without sound."""
        self.audio_warning.setText(text)
        self.audio_warning.setToolTip(text)
        self.audio_warning.setVisible(bool(text))

    def _on_files_dropped(self, paths: Sequence[Path], row: int) -> None:
        self.receive_files(paths, photo_index=None if row < 0 else row)

    def _on_files_dropped_on_music(self, paths: Sequence[Path], position: int) -> None:
        self.receive_files(paths, song_index=None if position < 0 else position)

    def receive_files(
        self, paths: Sequence[Path], *, photo_index: int | None = None, song_index: int | None = None
    ) -> None:
        """A drop anywhere: a .pmk is opened, audio files go to the music, the rest are photos."""
        dropped = sort_dropped(paths)
        if dropped.projects:
            self.open_path(dropped.projects[0])
            return
        if dropped.songs:
            self.add_songs(dropped.songs, song_index)
        if dropped.photos:
            self.import_paths(list(dropped.photos), photo_index)

    def _on_export_finished(self, _result: object) -> None:
        self._refresh_actions()

    def _on_missing_changed(self) -> None:
        missing = self.files.missing_ids()
        self.model.set_missing(missing)
        self.music_strip.model.set_missing(missing)
        self.song_panel.set_missing(missing)
        self._refresh_actions()

    def _refresh_title(self) -> None:
        self.setWindowTitle(self.files.window_title())
        self.setWindowModified(self.files.modified)

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.files.recent()
        for path in recent:
            action = self.recent_menu.addAction(path.stem)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _checked=False, p=path: self.open_path(p))
        if not recent:
            empty = self.recent_menu.addAction(self.tr("Cap projecte recent"))
            empty.setEnabled(False)

    def _on_import_started(self) -> None:
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText(self.tr("Important…"))
        self.progress_widget.setVisible(True)

    def _on_import_progress(self, done: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)
        self.progress_label.setText(self.tr("Important {done} de {total}…").format(done=done, total=total))

    def _on_import_finished(self, added: int) -> None:
        self.progress_widget.setVisible(False)
        self.refresh_status()
        if added:
            self.view.schedule_thumbnails()

    def _refresh_actions(self) -> None:
        has_selection = bool(self.view.selected_rows())
        for action in (
            self.delete_action,
            self.duplicate_action,
            self.move_left_action,
            self.move_right_action,
            self.rotate_left_action,
            self.rotate_right_action,
        ):
            action.setEnabled(has_selection)
        photos = self.controller.project.photos
        has_photos = bool(photos)
        motion = self.controller.project.motion_enabled
        # Like the photo panel's button: with camera motion off it would only undo the manual choices.
        self.reroll_action.setEnabled(has_selection and motion)
        self.reroll_all_action.setEnabled(has_photos and motion)
        self.reset_motions_action.setEnabled(any(p.motion.mode is MotionMode.MANUAL for p in photos))
        self.select_all_action.setEnabled(has_photos)
        self.sort_by_date_action.setEnabled(has_photos)
        self.sort_by_name_action.setEnabled(has_photos)
        self.undo_action.setEnabled(self.controller.can_undo)
        self.redo_action.setEnabled(self.controller.can_redo)
        has_songs = bool(self.controller.project.music.songs)
        self.fit_to_music_action.setEnabled(has_photos and has_songs)
        self.export_action.setEnabled(has_photos and not self.video_export.running)
        self.find_missing_action.setEnabled(bool(self.files.missing_ids()))

    def refresh_status(self) -> None:
        """ "124 fotos · 4:30" (§1.3): the total is the sum of the photo durations."""
        project = self.controller.project
        total = sum(project.photo_duration(photo) for photo in project.photos)
        count = len(project.photos)
        text = self.tr("1 foto · {duration}") if count == 1 else self.tr("{photos} fotos · {duration}")
        self.status_label.setText(text.format(photos=count, duration=clock(total)))
        self.duration_status.refresh(project)

    # --- Window ----------------------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt)
        """§1.1: files and folders can be dropped anywhere in the window."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt)
        """Photos, songs (§1.7) or a .pmk to open (§1.10)."""
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.receive_files(paths)
            event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt)
        """§1.10: asks to save the changes; the recovery copy goes away on a clean exit."""
        if self.youtube_window is not None and not self.youtube_window.close():
            event.ignore()  # downloads from YouTube in progress, and the user kept them
            return
        if self.record_window is not None and not self.record_window.close():
            event.ignore()  # a recording in progress, and the user kept it (G1)
            return
        if self.video_export.running or not self.files.maybe_save():
            event.ignore()
            return
        self.files.shutdown()
        self.songs.wait(5_000)
        self.music_strip.close_strip()
        self.importer.cancel()
        self.importer.wait(5_000)
        self.player_panel.close_panel()
        self.help.close()
        self.model.close()
        self.panel.close_panel()
        self.photo_panel.close_panel()
        self.song_panel.close_panel()
        self._service.cancel_pending()
        super().closeEvent(event)
