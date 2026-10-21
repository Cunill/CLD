"""Fixtures for the B5 thumbnail tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from passimaker.images import ImageSource
from passimaker.thumbs import ThumbnailService
from tests.unit.thumbs.helpers import RecordingSource

type ServiceFactory = Callable[..., ThumbnailService]


@pytest.fixture
def source() -> Iterator[RecordingSource]:
    recording = RecordingSource()
    yield recording
    recording.close()


@pytest.fixture
def make_service(tmp_path: Path) -> Iterator[ServiceFactory]:
    """Creates services that are closed at the end of the test (cache in tmp_path/cache by default)."""
    created: list[ThumbnailService] = []

    def factory(
        image_source: ImageSource, cache_dir: Path | None = None, **kwargs: object
    ) -> ThumbnailService:
        service = ThumbnailService(cache_dir or tmp_path / "cache", image_source, **kwargs)  # type: ignore[arg-type]
        created.append(service)
        return service

    yield factory
    for service in created:
        service.close()
