"""Fixtures shared by the interface tests: a window with fake services, closed when done."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from passimaker.export import CACHE_ENV_VAR
from passimaker.model import ProjectController
from passimaker.ui.main_window import MainWindow
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with, images

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def isolated_user_files(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Recent projects, recovery copy and caches go to a temporary folder, never the user's."""
    folder = tmp_path_factory.mktemp("usuari")
    monkeypatch.setenv(CACHE_ENV_VAR, str(folder / "cache"))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(folder / "config"))
    return folder


@pytest.fixture
def questions() -> RecordedQuestions:
    return RecordedQuestions()


@pytest.fixture
def thumbnails() -> Iterator[FakeThumbnailService]:
    service = FakeThumbnailService()
    yield service
    service.close()


def build_window(
    qtbot: QtBot,
    controller: ProjectController,
    thumbnails: FakeThumbnailService,
    questions: RecordedQuestions,
    *,
    size: tuple[int, int] = (1100, 700),
) -> MainWindow:
    window = MainWindow(controller, thumbnails, images(), questions)
    window.resize(*size)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def window(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> Iterator[MainWindow]:
    """An empty window: the tests add the photos they need."""
    made = build_window(qtbot, controller_with(0), thumbnails, questions)
    yield made
    made.close()


@pytest.fixture
def window_with_photos(
    qtbot: QtBot, thumbnails: FakeThumbnailService, questions: RecordedQuestions
) -> Iterator[MainWindow]:
    """A window with twelve photos already in the storyboard."""
    made = build_window(qtbot, controller_with(12), thumbnails, questions)
    yield made
    made.close()
