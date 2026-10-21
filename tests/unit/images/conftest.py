"""Fixtures for B4 image tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.images.samples import make_samples


@pytest.fixture(scope="session")
def samples(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Extra B4 sample photos (see samples.py), created once per test session."""
    return make_samples(tmp_path_factory.mktemp("b4_samples"))
