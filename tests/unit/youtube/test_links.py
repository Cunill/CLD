"""C01: recognising pasted YouTube links (pure, no network)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from passimaker.youtube import parse_link, watch_url

ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "text",
    [
        f"https://www.youtube.com/watch?v={ID}",
        f"http://youtube.com/watch?v={ID}",
        f"youtube.com/watch?v={ID}",
        f"https://m.youtube.com/watch?v={ID}&t=30s",
        f"https://www.youtube.com/watch?v={ID}&list=PL1234567890&index=3",
        f"https://www.youtube.com/watch?feature=share&v={ID}",
        f"https://music.youtube.com/watch?v={ID}&si=abc",
        f"https://youtu.be/{ID}",
        f"https://youtu.be/{ID}?t=42",
        f"https://www.youtube.com/shorts/{ID}",
        f"https://www.youtube.com/embed/{ID}",
        f"https://www.youtube.com/live/{ID}?feature=share",
        f"  https://WWW.YouTube.com/watch?v={ID}  \n",
    ],
)
def test_valid_links(text: str) -> None:
    assert parse_link(text) == ID


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Ludovico Einaudi Nuvole Bianche",
        ID,
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        f"https://www.youtube.com/watch?v={ID}x",
        "https://www.youtube.com/playlist?list=PL1234567890",
        "https://www.youtube.com/@canal",
        f"https://vimeo.com/watch?v={ID}",
        f"https://youtube.com.example.org/watch?v={ID}",
        f"ftp://youtube.com/watch?v={ID}",
        f"https://youtu.be/{ID}/extra",
        f"https://www.youtube.com/watch?v={ID}&v=aaaaaaaaaaa",
        "https://[::1/watch",
    ],
)
def test_other_text_is_not_a_link(text: str) -> None:
    assert parse_link(text) is None


ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
video_ids = st.text(alphabet=ID_ALPHABET, min_size=11, max_size=11)


@given(video_ids)
def test_the_canonical_url_round_trips(video_id: str) -> None:
    assert parse_link(watch_url(video_id)) == video_id


@given(st.text(max_size=80))
def test_never_crashes_and_only_returns_valid_ids(text: str) -> None:
    found = parse_link(text)
    assert found is None or (len(found) == 11 and found in text)
