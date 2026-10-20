"""Fixtures of the model tests."""

from __future__ import annotations

import pytest

from passi import timeline
from tests.unit.model.helpers import proportional_fit


@pytest.fixture
def fake_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    """timeline.fit_to_music is block B2 (developed in parallel): use a proportional stand-in."""
    monkeypatch.setattr(timeline, "fit_to_music", proportional_fit)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """TEMPORARY (B1 diagnosis): failures as GitHub annotations, readable through the API."""
    import os

    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for report in terminalreporter.stats.get("failed", []) + terminalreporter.stats.get("error", []):
        text = str(getattr(report, "longrepr", ""))[-6000:]
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        title = report.nodeid.replace("%", "%25").replace(":", "%3A").replace(",", "%2C")
        terminalreporter.write_line(f"::error title={title}::{text}")
