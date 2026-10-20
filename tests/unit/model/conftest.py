"""Fixtures of the model tests."""

from __future__ import annotations

import pytest

from passi import timeline
from tests.unit.model.helpers import proportional_fit


@pytest.fixture
def fake_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    """timeline.fit_to_music is block B2 (developed in parallel): use a proportional stand-in."""
    monkeypatch.setattr(timeline, "fit_to_music", proportional_fit)
