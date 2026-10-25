"""Fixtures of the YouTube module tests: no consent between tests, the fake backend, a blocked network."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from passimaker.youtube import consent
from passimaker.youtube.consent import ConsentToken
from tests.fakes.youtube import FakeYoutubeBackend


@pytest.fixture(autouse=True)
def _no_consent() -> Iterator[None]:
    consent.revoke()
    yield
    consent.revoke()


@pytest.fixture
def token() -> ConsentToken:
    return consent.grant()


@pytest.fixture
def fake() -> FakeYoutubeBackend:
    return FakeYoutubeBackend()


class NetworkAttemptError(AssertionError):
    """Raised by the blocked socket functions: something tried to connect."""


@pytest.fixture
def network_attempts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Blocks the network (ESPECIFICACIO §1.7 bis, decision 0012) and records every attempt.

    socket.socket.connect / connect_ex, socket.create_connection and socket.getaddrinfo fail;
    a test that expects no connection asserts the returned list is empty.
    """
    attempts: list[str] = []

    def blocked(name: str) -> Any:
        def refuse(*args: object, **kwargs: object) -> Any:
            attempts.append(f"{name}{args[1:] if name.startswith('socket.') else args}")
            raise NetworkAttemptError(f"network attempt: {name}")

        return refuse

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("getaddrinfo"))
    return attempts
