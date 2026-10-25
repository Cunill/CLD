"""C01: the consent to the YouTube notice lives only in memory and gates every network function."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from passimaker import youtube
from passimaker.youtube import consent


@pytest.fixture(autouse=True)
def _no_consent() -> Iterator[None]:
    consent.revoke()
    yield
    consent.revoke()


def test_there_is_no_consent_until_it_is_granted() -> None:
    assert consent.current() is None
    token = consent.grant()
    assert consent.current() is token
    assert consent.grant() is token  # one consent per run of the program, shared by every window


def test_a_token_cannot_be_forged() -> None:
    with pytest.raises(TypeError):
        consent.ConsentToken(object(), 1)


def test_revoking_invalidates_the_old_token() -> None:
    old = consent.grant()
    consent.revoke()
    assert consent.current() is None and not consent.is_valid(old)
    assert consent.grant() is not old
    assert not consent.is_valid(old)


def _calls(token: object, tmp_path: Path) -> list[Callable[[], object]]:
    return [
        lambda: youtube.search(token, "Nuvole bianche"),  # type: ignore[arg-type]
        lambda: youtube.resolve(token, "dQw4w9WgXcQ"),  # type: ignore[arg-type]
        lambda: youtube.fetch_thumbnail(token, "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"),  # type: ignore[arg-type]
        lambda: youtube.download_audio(token, "dQw4w9WgXcQ", tmp_path),  # type: ignore[arg-type]
    ]


@pytest.mark.parametrize("index", range(4))
def test_network_functions_refuse_to_work_without_consent(index: int, tmp_path: Path) -> None:
    stale = consent.grant()
    consent.revoke()
    for token in (None, stale, "token"):
        with pytest.raises(youtube.YoutubeConsentError) as error:
            _calls(token, tmp_path)[index]()
        assert error.value.message_key == youtube.ERROR_CONSENT


@pytest.mark.parametrize("index", range(4))
def test_with_consent_they_reach_the_part_of_block_c03(index: int, tmp_path: Path) -> None:
    token = consent.grant()
    with pytest.raises(NotImplementedError):
        _calls(token, tmp_path)[index]()
