"""B16 · Polish: the Ajuda menu, the shortcuts, the tooltips, the empty state, the singulars and the
warning when the preview has no music."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from pytestqt.qtbot import QtBot

from passimaker import __version__
from passimaker.audio import AudioSource
from passimaker.common import PassiMakerError
from passimaker.model import Project, ProjectController
from passimaker.model.commands import AddSongs
from passimaker.model.types import Song
from passimaker.ui.dialogs import DialogQuestions
from passimaker.ui.help import about_html, guide_html, shortcuts
from passimaker.ui.main_window import MainWindow
from passimaker.ui.player_panel import PlayerPanel
from tests.fakes.audio import ToneAudioSource
from tests.ui.conftest import build_window
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with, images
from tests.unit.preview.fakes import FakeAudioOutput, SimulatedClockFactory

pytestmark = pytest.mark.ui

TIMEOUT_MS = 20_000


def portable(keys: QKeySequence) -> str:
    return keys.toString(QKeySequence.SequenceFormat.PortableText)


# --- Ajuda ---------------------------------------------------------------------------------------


def test_the_help_menu_has_the_guide_and_about(window: MainWindow) -> None:
    assert window.help_menu.menuAction() in window.menuBar().actions()
    assert window.help_menu.title() == "Ajuda"
    assert window.guide_action in window.help_menu.actions()
    assert window.about_action in window.help_menu.actions()
    assert window.guide_action.shortcut() == QKeySequence(QKeySequence.StandardKey.HelpContents)


def test_the_guide_opens_without_blocking_and_only_once(window: MainWindow) -> None:
    window.guide_action.trigger()
    guide = window.help.guide
    assert guide is not None and guide.isVisible()
    assert not guide.isModal()
    text = guide.browser.toPlainText()
    for words in ("1. Fotos", "2. Música", "3. Exportar", "Dreceres de teclat", ".pmk"):
        assert words in text
    window.guide_action.trigger()
    assert window.help.guide is guide


def test_the_guide_explains_youtube_recording_and_their_mishaps(window: MainWindow) -> None:
    window.guide_action.trigger()
    guide = window.help.guide
    assert guide is not None
    text = guide.browser.toPlainText()
    for words in (
        "Música de YouTube",
        "Des de YouTube…",
        "Gravar el que sona",
        "Grava el que sona…",
        "YouTube ha canviat",
        "No s'ha gravat cap so",
    ):
        assert words in text
    assert "avís legal" not in text.lower()  # G2: recording has no legal notice


def test_the_guide_explains_the_version_1_3_features(window: MainWindow) -> None:
    window.guide_action.trigger()
    guide = window.help.guide
    assert guide is not None
    text = guide.browser.toPlainText()
    for words in (
        "Quadres negres a l'inici i al final",
        "Afegeix negre a l'inici",
        "Barreja les fotos",
        "Format: 16:9 ▾",
        "9:16",
        "2:3",
        "3:4",
        "Silenci abans",
        "Silenci després",
        "Tota la música",
        "entre 0,4 i 24 segons",
        "doble clic",
    ):
        assert words in text


def test_the_guide_names_match_the_window_texts(window: MainWindow) -> None:
    assert window.shuffle_action.text() == "Barreja les fotos"
    assert window.black_start_action.text() == "Afegeix negre a l'inici"
    assert window.black_end_action.text() == "Afegeix negre al final"


def test_the_about_window_names_the_new_components(window: MainWindow) -> None:
    html = about_html(None)
    for name in ("yt-dlp", "Deno", "soundcard"):
        assert name in html


def test_the_guide_lists_every_shortcut_of_the_window(window: MainWindow) -> None:
    listed = {portable(row.keys) for row in shortcuts()}
    used: list[list[str]] = []
    for action in window.findChildren(QAction):
        keys = [portable(k) for k in action.shortcuts() if not k.isEmpty()]
        if keys:
            used.append(keys)
    for shortcut in window.findChildren(QShortcut):
        if not shortcut.key().isEmpty():
            used.append([portable(shortcut.key())])
    assert used
    missing = [keys for keys in used if not set(keys) & listed]
    assert missing == []
    text = guide_html()
    for row in shortcuts():
        assert row.description in text


def test_about_shows_the_version_and_the_log_folder(window: MainWindow, tmp_path: Path) -> None:
    window.about_action.trigger()
    about = window.help.about
    assert about is not None and about.isVisible()
    assert f"PassiMaker {__version__}" in about.browser.toPlainText()
    assert str(tmp_path) in about_html(tmp_path)
    assert "Registre" not in about_html(None)


def test_quit_closes_the_window(window: MainWindow) -> None:
    assert window.quit_action.shortcut() == QKeySequence("Ctrl+Q")
    window.quit_action.trigger()
    assert not window.isVisible()


def test_the_help_windows_close_with_the_main_window(window: MainWindow) -> None:
    window.guide_action.trigger()
    window.about_action.trigger()
    window.close()
    assert window.help.guide is not None and not window.help.guide.isVisible()
    assert window.help.about is not None and not window.help.about.isVisible()


# --- Tooltips and empty state --------------------------------------------------------------------


def test_the_toolbar_actions_explain_themselves(window: MainWindow) -> None:
    for action in window.toolbar.actions():
        if action.isSeparator():
            continue
        tip = action.toolTip()
        assert tip and tip != action.text().replace("&", ""), action.text()


def test_the_panel_fields_have_tooltips(window: MainWindow) -> None:
    panel = window.panel
    for widget in (panel.duration, panel.crossfade, panel.intensity, panel.output_format, panel.zoom_amount):
        assert widget.toolTip()
    photo = window.photo_panel
    for widget in (photo.duration, photo.motion, photo.fit):
        assert widget.toolTip()
    song = window.song_panel
    for widget in (song.fade_in_enabled, song.fade_out_enabled, song.trim_start, song.volume, song.listen):
        assert widget.toolTip()


def test_the_empty_state_names_the_three_steps(window: MainWindow) -> None:
    steps = window.storyboard.empty.steps.text()
    assert "Fotos" in steps and "Música" in steps and "Exportar vídeo" in steps
    assert "F1" in steps


# --- Singulars -----------------------------------------------------------------------------------


def test_one_photo_is_singular_in_the_status_bar(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> None:
    window = build_window(qtbot, controller_with(1), thumbnails, questions)
    assert window.status_label.text() == "1 foto · 0:02"


def test_one_missing_file_is_singular(qtbot: QtBot) -> None:
    dialogs = DialogQuestions()
    qtbot.addWidget(dialogs)
    assert dialogs.relink_box(1).text() == "No es troba 1 fitxer."
    assert dialogs.relink_box(3).text() == "No es troben 3 fitxers."


# --- The preview without music -------------------------------------------------------------------


def song() -> Song:
    return Song("s1", Path("/musica/1.mp3"), None, 120.0)


@pytest.fixture
def failing_panel(qtbot: QtBot) -> Iterator[tuple[PlayerPanel, ProjectController, list[bool]]]:
    """A panel whose music fails while `fail[0]` is true."""
    controller = controller_with(3)
    output = FakeAudioOutput()
    fail = [True]

    def preparer(project: Project) -> AudioSource | None:
        if fail[0]:
            raise PassiMakerError("ffmpeg.not_found")
        return ToneAudioSource(60.0) if project.music.songs else None

    panel = PlayerPanel(
        controller,
        images(),
        output=output,
        audio_preparer=preparer,
        clock_factory=SimulatedClockFactory(output.clock),
    )
    qtbot.addWidget(panel)
    yield panel, controller, fail
    panel.close_panel()


def test_the_panel_says_why_the_preview_has_no_music(
    qtbot: QtBot, failing_panel: tuple[PlayerPanel, ProjectController, list[bool]]
) -> None:
    panel, controller, fail = failing_panel
    with qtbot.waitSignal(panel.audio_problem, timeout=TIMEOUT_MS) as blocker:
        controller.execute(AddSongs((song(),)))
    assert blocker.args is not None
    assert blocker.args[0] == (
        "⚠ La previsualització sona sense música: No s'ha trobat FFmpeg. Torna a descomprimir el programa."
    )
    fail[0] = False
    with qtbot.waitSignal(panel.audio_problem, timeout=TIMEOUT_MS) as blocker:
        panel.reload_audio()
    assert blocker.args == [""]
    assert panel.audio is not None


def test_an_unexpected_failure_also_has_a_message(qtbot: QtBot) -> None:
    controller = controller_with(2)
    output = FakeAudioOutput()

    def preparer(_project: Project) -> AudioSource | None:
        raise RuntimeError("boom")

    panel = PlayerPanel(
        controller,
        images(),
        output=output,
        audio_preparer=preparer,
        clock_factory=SimulatedClockFactory(output.clock),
    )
    qtbot.addWidget(panel)
    try:
        with qtbot.waitSignal(panel.audio_problem, timeout=TIMEOUT_MS) as blocker:
            controller.execute(AddSongs((song(),)))
        assert blocker.args is not None
        assert "error inesperat" in blocker.args[0]
    finally:
        panel.close_panel()


def test_the_status_bar_shows_the_music_warning(window: MainWindow) -> None:
    window.player_panel.audio_problem.emit("⚠ La previsualització sona sense música: motiu")
    assert window.audio_warning.isVisibleTo(window)
    assert "motiu" in window.audio_warning.text()
    window.player_panel.audio_problem.emit("")
    assert not window.audio_warning.isVisibleTo(window)


def test_the_guide_ends_with_the_unforeseen_section(window: MainWindow) -> None:
    text = guide_html()
    assert text.rindex("Imprevistos") > text.rindex("Dreceres de teclat")
    assert "tres voltes a la cadira" in text
