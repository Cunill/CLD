"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Qt tests run without a display (also on the Windows CI runner).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def fixture_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """All generated test photos and audio, created once per test session."""
    from tests.fixtures.generate import generate_all

    return generate_all(tmp_path_factory.mktemp("fixtures"))
