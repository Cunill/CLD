"""Preview panel (§1.8): the player's frame, ▶/❚❚, previous and next photo, and the time bar.

The panel owns the Player (passimaker.preview) and keeps it in step with the project: every
change builds a new timeline and compositor (a few milliseconds even with 1.000 photos) and
hands them to the player, which redraws at once in pause and goes on playing otherwise. The
music is prepared on a worker thread (decoding can take seconds) and replaces the sound when it
is ready; until then the previous sound, or the internal clock, keeps the time.

Keys (decision of B13, see docs/sessions/B13.md):
- Space plays and pauses from anywhere in the window, except while typing in a text box.
- ← and → go to the previous and next photo when the panel has the focus. In the storyboard the
  arrows keep moving the selection, and selecting a photo takes the preview there, so the arrows
  do the same thing in both places. Ctrl+← and Ctrl+→ still move photos in the storyboard.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QMouseEvent, QPainter, QPaintEvent, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from passimaker.audio import AudioSource, prepare
from passimaker.common import PassiMakerError, RGBImage
from passimaker.export import cache_root
from passimaker.images import ImageSource
from passimaker.model import Change, Photo, Project, ProjectController
from passimaker.model.types import Rotation
from passimaker.preview import (
    PREVIEW_MAX_SIZE,
    AudioOutput,
    ClockFactory,
    MonotonicClock,
    Player,
    same_place,
)
from passimaker.render import Compositor, IntermediateProvider
from passimaker.timeline import Timeline, compute_timeline, frame_to_time, time_to_frame
from passimaker.ui.formatting import clock

_log = logging.getLogger(__name__)

type AudioPreparer = Callable[[Project], AudioSource | None]
"""Builds the sound of a project (None without music). Runs on a worker thread."""

MIN_FRAME_SIDE = 16
CONTROL_ICON = QSize(20, 20)
RECENT_INTERMEDIATES = 8
"""Intermediates kept in memory by the panel (~6 MB each): see RecentIntermediates."""


class RecentIntermediates:
    """The last intermediates used, in memory.

    Every edit builds a new compositor, which starts with no canvases: without this, the photo on
    screen would be read from disk again after every change of duration or motion.
    """

    def __init__(self, provider: IntermediateProvider, capacity: int = RECENT_INTERMEDIATES) -> None:
        self._provider = provider
        self._capacity = capacity
        self._lock = threading.Lock()
        self._images: OrderedDict[tuple[str, Path, Rotation], RGBImage] = OrderedDict()

    def __call__(self, photo: Photo) -> RGBImage:
        key = (photo.id, photo.path, photo.rotation)
        with self._lock:
            image = self._images.get(key)
            if image is not None:
                self._images.move_to_end(key)
                return image
        image = self._provider(photo)
        with self._lock:
            self._images[key] = image
            while len(self._images) > self._capacity:
                self._images.popitem(last=False)
        return image


def prepare_preview_audio(project: Project) -> AudioSource | None:
    """The real mix (passimaker.audio), with the decoded songs in the shared cache folder."""
    if not project.music.songs:
        return None
    timeline = compute_timeline(project)
    return prepare(project, timeline.audio_plan, cache_root() / "audio")


def frame_size(project: Project, available: QSize) -> tuple[int, int]:
    """Largest frame with the video's proportion that fits the widget and PREVIEW_MAX_SIZE."""
    width, height = project.output_format.size
    limit_w, limit_h = PREVIEW_MAX_SIZE if width >= height else PREVIEW_MAX_SIZE[::-1]
    scale = min(max(1, available.width()) / width, max(1, available.height()) / height)
    scale = min(scale, limit_w / width, limit_h / height)
    return max(MIN_FRAME_SIDE, round(width * scale)), max(MIN_FRAME_SIDE, round(height * scale))


class FrameView(QWidget):
    """The last frame of the player, letterboxed on black."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image: QImage | None = None
        self.setMinimumSize(240, 135)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def show_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt)
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        image = self.image
        if image is None or image.isNull():
            return
        size = image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect(
            (self.width() - size.width()) // 2,
            (self.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, image)


class TimeBar(QSlider):
    """Time bar in frames: a click jumps to the point clicked (not one page step)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setRange(0, 0)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self
            )
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self
            )
            span = max(1, groove.width() - handle.width())
            x = round(event.position().x()) - groove.x() - handle.width() // 2
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x, span)
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class _AudioSignals(QObject):
    ready = Signal(int, object)


class PlayerPanel(QWidget):
    """The preview area of §1.0: the frame and the controls of §1.8."""

    def __init__(
        self,
        controller: ProjectController,
        images: ImageSource,
        intermediate: IntermediateProvider | None = None,
        parent: QWidget | None = None,
        *,
        output: AudioOutput | None = None,
        audio_preparer: AudioPreparer = prepare_preview_audio,
        clock_factory: ClockFactory = MonotonicClock,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._images = images
        self._intermediate = None if intermediate is None else RecentIntermediates(intermediate)
        self._prepare_audio = audio_preparer
        self._audio: AudioSource | None = None
        self._audio_generation = 0
        self._audio_threads: list[threading.Thread] = []
        self._audio_signals = _AudioSignals(self)
        self._audio_signals.ready.connect(self._on_audio_ready)
        self._shown_photo: str | None = None
        self._size = (0, 0)

        project = controller.project
        timeline = compute_timeline(project)
        self._timeline = timeline
        self._frames = self._compositor(project, timeline)
        self.view = FrameView()
        self.player = Player(
            self._frames,
            timeline,
            None,
            output,
            self,
            clock_factory=clock_factory,
            size=frame_size(project, self.view.size()),
        )
        self._build_controls()
        self._build_shortcuts()
        self.player.frame_ready.connect(self._on_frame)
        self.player.state_changed.connect(self._on_state)
        self._unsubscribe = controller.subscribe(self._on_changes)
        self._update_time(0.0)
        self._update_play_button(False)
        if project.music.songs:
            self.reload_audio()

    # --- Layout ----------------------------------------------------------------------------------

    def _build_controls(self) -> None:
        self.previous_button = self._button(
            QStyle.StandardPixmap.SP_MediaSkipBackward, self.tr("Foto anterior (←)")
        )
        self.play_button = self._button(QStyle.StandardPixmap.SP_MediaPlay, self.tr("Reprodueix (espai)"))
        self.next_button = self._button(
            QStyle.StandardPixmap.SP_MediaSkipForward, self.tr("Foto següent (→)")
        )
        self.previous_button.clicked.connect(self.previous_photo)
        self.play_button.clicked.connect(self.toggle_play)
        self.next_button.clicked.connect(self.next_photo)
        self.time_bar = TimeBar()
        self.time_bar.sliderMoved.connect(self._on_bar_moved)
        self.time_label = QLabel()
        self.time_label.setMinimumWidth(80)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        controls = QHBoxLayout()
        controls.setContentsMargins(4, 2, 4, 2)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.time_bar, 1)
        controls.addWidget(self.time_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view, 1)
        layout.addLayout(controls)

    def _button(self, icon: QStyle.StandardPixmap, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(CONTROL_ICON)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Space is the play key, not "click the button"
        return button

    def _build_shortcuts(self) -> None:
        self.play_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.play_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.play_shortcut.activated.connect(self.toggle_play)
        self.previous_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.previous_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.previous_shortcut.activated.connect(self.previous_photo)
        self.next_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.next_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.next_shortcut.activated.connect(self.next_photo)

    # --- Public ----------------------------------------------------------------------------------

    def toggle_play(self) -> None:
        self.player.toggle()
        self._update_play_button(self.player.playing)

    def previous_photo(self) -> None:
        self._go_to_photo(self.player.photo_index - 1)

    def next_photo(self) -> None:
        self._go_to_photo(self.player.photo_index + 1)

    def show_photo(self, photo_id: str | None) -> None:
        """Clicking a thumbnail: the preview jumps to that photo (and keeps playing if it was)."""
        if photo_id is None or photo_id == self._shown_photo:
            return
        for slot in self._timeline.slots:
            if slot.photo_id == photo_id:
                self._shown_photo = photo_id
                self.player.seek_photo(slot.index)
                return

    def reload_audio(self) -> None:
        """Prepares the music again and gives it to the player (for a change of the music).

        The panel already does it when the controller reports a change of the music or of the
        timing; this is for changes the controller cannot see (B11: a song found again on disk).
        """
        self._audio_generation += 1
        generation = self._audio_generation
        project = self._controller.project
        if not project.music.songs:
            self._on_audio_ready(generation, None)
            return
        thread = threading.Thread(
            target=self._prepare_in_background, args=(generation, project), name="passimaker-preview-audio"
        )
        thread.daemon = True
        self._audio_threads = [t for t in self._audio_threads if t.is_alive()] + [thread]
        thread.start()

    @property
    def frame(self) -> QImage | None:
        """The frame on screen (tests and screenshots)."""
        return self.view.image

    @property
    def audio(self) -> AudioSource | None:
        return self._audio

    def wait(self, timeout_ms: int = 10_000) -> bool:
        """Waits until the music is prepared and the player is paused with nothing to draw."""
        for thread in list(self._audio_threads):
            thread.join(timeout_ms / 1000)
        return self.player.wait_idle(timeout_ms / 1000)

    def close_panel(self) -> None:
        self._unsubscribe()
        self._audio_generation += 1
        self.player.close()

    # --- Reactions -------------------------------------------------------------------------------

    def _on_changes(self, changes: frozenset[Change]) -> None:
        if not changes - {Change.SAVED_STATE}:
            return
        self._rebuild()
        if changes & {Change.MUSIC, Change.TIMING, Change.PHOTOS, Change.SETTINGS} and (
            self._controller.project.music.songs or self._audio is not None
        ):
            self.reload_audio()

    def _rebuild(self) -> None:
        project = self._controller.project
        timeline = compute_timeline(project)
        old, self._timeline = self._timeline, timeline
        self._frames = self._compositor(project, timeline)
        # In pause the preview stays on its photo; playing, the sound is the clock and goes on.
        at = None if self.player.playing else same_place(old, timeline, self.player.position)
        self.player.set_scene(self._frames, timeline, self._audio, at)
        self._apply_size()
        self._update_time(self.player.position)

    def _compositor(self, project: Project, timeline: Timeline) -> Compositor:
        return Compositor(project, timeline, self._images, self._intermediate)

    def _prepare_in_background(self, generation: int, project: Project) -> None:
        try:
            audio = self._prepare_audio(project)
        except PassiMakerError as error:
            # A log line, not a message on screen (B11/B14 show the music errors): no tr().
            _log.log(logging.WARNING, "No s'ha pogut preparar la música: %s", error.message_key)
            audio = None
        except Exception:
            _log.exception("No s'ha pogut preparar la música de la previsualització")
            audio = None
        with contextlib.suppress(RuntimeError):  # the panel may have been closed meanwhile
            self._audio_signals.ready.emit(generation, audio)

    def _on_audio_ready(self, generation: int, audio: object) -> None:
        if generation != self._audio_generation:
            return
        self._audio = cast("AudioSource | None", audio)
        self.player.set_scene(self._frames, self._timeline, self._audio)

    def _go_to_photo(self, index: int) -> None:
        count = len(self._timeline.slots)
        if count == 0:
            return
        index = max(0, min(count - 1, index))
        self._shown_photo = self._timeline.slots[index].photo_id
        self.player.seek_photo(index)

    def _on_bar_moved(self, frame: int) -> None:
        t = frame_to_time(frame, self._timeline.fps)
        self.player.seek(t)
        self._update_time(t, move_bar=False)

    def _on_frame(self, image: object, t: float) -> None:
        if isinstance(image, QImage):
            self.view.show_image(image)
        self._update_time(t)

    def _on_state(self, playing: bool, t: float, photo_index: int) -> None:
        self._update_play_button(self.player.playing)

    def _update_play_button(self, playing: bool) -> None:
        pixmap = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(pixmap))
        self.play_button.setToolTip(self.tr("Pausa (espai)") if playing else self.tr("Reprodueix (espai)"))

    def _update_time(self, t: float, *, move_bar: bool = True) -> None:
        timeline = self._timeline
        last = max(0, timeline.total_frames - 1)
        if move_bar and not self.time_bar.isSliderDown():
            self.time_bar.blockSignals(True)
            self.time_bar.setRange(0, last)
            self.time_bar.setValue(min(last, time_to_frame(t, timeline.fps)))
            self.time_bar.blockSignals(False)
        self.time_label.setText(
            self.tr("{current} / {total}").format(
                current=clock(min(t, timeline.total_duration_s)), total=clock(timeline.total_duration_s)
            )
        )

    def _apply_size(self) -> None:
        size = frame_size(self._controller.project, self.view.size())
        if size != self._size:
            self._size = size
            self.player.set_size(*size)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._apply_size()
