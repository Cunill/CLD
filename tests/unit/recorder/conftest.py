"""Fixtures of the recorder tests: plenty of free space unless a test says otherwise."""

from __future__ import annotations

import pytest

from passimaker.recorder import capture


@pytest.fixture(autouse=True)
def _plenty_of_space(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "free_bytes", lambda folder: 100 * 1024**3)
