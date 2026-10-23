"""The properties area under the preview (§1.0): the project, the selected photos or the song.

Three tabs. Selecting photos in the storyboard opens "Foto" and selecting a song in the music
strip opens "Cançó"; the project tab is always there. A tab with nothing selected is disabled.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea, QTabWidget, QWidget

from passimaker.ui.photo_panel import PhotoPanel
from passimaker.ui.project_panel import ProjectPanel
from passimaker.ui.song_panel import SongPanel


def scrolled(panel: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(panel)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area


class PropertiesPanel(QTabWidget):
    PROJECT = 0
    PHOTO = 1
    SONG = 2

    def __init__(
        self, project: ProjectPanel, photo: PhotoPanel, song: SongPanel, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.project_panel = project
        self.photo_panel = photo
        self.song_panel = song
        self.addTab(scrolled(project), self.tr("Projecte"))
        self.addTab(scrolled(photo), self.tr("Foto"))
        self.addTab(scrolled(song), self.tr("Cançó"))
        self.refresh_tabs()

    def show_photos(self, photo_ids: tuple[str, ...]) -> None:
        self.photo_panel.show_photos(photo_ids)
        if photo_ids:
            self.setTabEnabled(self.PHOTO, True)
            self.setCurrentIndex(self.PHOTO)
        else:
            self._leave(self.PHOTO)

    def show_song(self, song_id: str | None) -> None:
        self.song_panel.show_song(song_id)
        if song_id is not None:
            self.setTabEnabled(self.SONG, True)
            self.setCurrentIndex(self.SONG)
        else:
            self._leave(self.SONG)

    def refresh_tabs(self) -> None:
        """After an edit: a photo or a song that was removed takes its tab away."""
        if not self.photo_panel.photo_ids:
            self._leave(self.PHOTO)
        if self.song_panel.song() is None:
            self._leave(self.SONG)

    def _leave(self, tab: int) -> None:
        if self.currentIndex() == tab:
            self.setCurrentIndex(self.PROJECT)
        self.setTabEnabled(tab, False)
