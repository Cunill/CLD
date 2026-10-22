"""Fixtures shared by the interface tests: a window with fake services, closed when done."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytestqt.qtbot import QtBot

from passimaker.model import ProjectController
from passimaker.ui.main_window import MainWindow
from tests.ui.helpers import FakeThumbnailService, RecordedQuestions, controller_with, images

pytestmark = pytest.mark.ui


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
