"""C03: search, resolve and fetch_thumbnail with the fake backend (contract §15)."""

from __future__ import annotations

from concurrent.futures import CancelledError

import pytest

from passimaker import youtube
from passimaker.common import CancelToken
from passimaker.model import defaults
from passimaker.youtube.consent import ConsentToken
from passimaker.youtube.search import MAX_SEARCH_RESULTS, THUMBNAIL_MAX_BYTES
from tests.fakes.youtube import FakeYoutubeBackend, numbered_id, search_entry, video_info

ID = "dQw4w9WgXcQ"


def _entries(count: int) -> list[dict[str, object]]:
    return [search_entry(numbered_id(i), f"Cançó {i}") for i in range(count)]


def test_search_returns_the_results_in_order(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.search_entries = _entries(15)
    results = youtube.search(token, "Ludovico Einaudi Nuvole Bianche", backend=fake)
    assert len(results) == defaults.YOUTUBE_RESULTS_PER_PAGE
    assert [r.video_id for r in results] == [numbered_id(i) for i in range(10)]
    first = results[0]
    assert first.title == "Cançó 0" and first.channel == "Canal" and first.duration_s == 200.0
    assert first.url == youtube.watch_url(first.video_id)
    assert first.thumbnail_url == f"https://i.ytimg.com/vi/{first.video_id}/mqdefault.jpg"
    assert not first.is_live
    assert fake.calls == ["extract_info ytsearch10:Ludovico Einaudi Nuvole Bianche flat=True"]


def test_more_results_skip_the_ones_already_shown(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.search_entries = _entries(25)
    page = youtube.search(token, "x", limit=10, offset=10, backend=fake)
    assert [r.video_id for r in page] == [numbered_id(i) for i in range(10, 20)]
    assert fake.calls[-1] == "extract_info ytsearch20:x flat=True"


def test_fewer_results_than_asked(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.search_entries = _entries(3)
    assert len(youtube.search(token, "x", backend=fake)) == 3
    assert youtube.search(token, "x", offset=10, backend=fake) == ()


def test_blank_query_and_the_limit_do_not_ask_youtube(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    assert youtube.search(token, "  \n ", backend=fake) == ()
    assert youtube.search(token, "x", offset=MAX_SEARCH_RESULTS, backend=fake) == ()
    assert fake.calls == []
    with pytest.raises(ValueError):
        youtube.search(token, "x", limit=0, backend=fake)
    with pytest.raises(ValueError):
        youtube.search(token, "x", offset=-1, backend=fake)


def test_spaces_in_the_query_are_tidied(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    youtube.search(token, "  Nuvole \t bianche ", backend=fake)
    assert fake.calls == ["extract_info ytsearch10:Nuvole bianche flat=True"]


def test_channels_and_playlists_are_left_out(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    channel = {"_type": "url", "ie_key": "YoutubeTab", "id": "UCabcdefghijklmnopqrstuv", "title": "Canal"}
    playlist = {"_type": "url", "ie_key": "YoutubeTab", "id": "PLabcdefghi", "title": "Llista"}
    fake.search_entries = [channel, search_entry(numbered_id(1)), playlist, {"title": "sense id"}]
    assert [r.video_id for r in youtube.search(token, "x", backend=fake)] == [numbered_id(1)]


def test_live_and_missing_duration_in_results(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    live = search_entry(numbered_id(1), duration=None) | {"live_status": "is_live"}
    upcoming = search_entry(numbered_id(2), duration=None) | {"live_status": "is_upcoming"}
    unknown = search_entry(numbered_id(3), duration=None) | {"title": None, "channel": None, "uploader": "Up"}
    fake.search_entries = [live, upcoming, unknown]
    results = youtube.search(token, "x", backend=fake)
    assert [r.is_live for r in results] == [True, True, False]
    assert all(r.duration_s is None for r in results)
    assert results[2].title == numbered_id(3) and results[2].channel == "Up"


def test_long_videos_are_listed(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    """The interface greys them out; search does not hide them (ESPECIFICACIO §1.7 bis)."""
    fake.search_entries = [search_entry(numbered_id(1), duration=3 * 3600.0)]
    assert youtube.search(token, "x", backend=fake)[0].duration_s == 3 * 3600.0


def test_search_cancelled(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    cancel = CancelToken()
    cancel.cancel()
    with pytest.raises(CancelledError):
        youtube.search(token, "x", cancel=cancel, backend=fake)
    assert fake.calls == []


def test_search_cancelled_while_waiting_for_youtube(token: ConsentToken) -> None:
    cancel = CancelToken()

    class Slow(FakeYoutubeBackend):
        def extract_info(self, url: str, *, flat: bool) -> dict[str, object]:
            cancel.cancel()  # the user pressed [Cancel·lar] while YouTube was answering
            return {"entries": _entries(3)}

    with pytest.raises(CancelledError):
        youtube.search(token, "x", cancel=cancel, backend=Slow())


def test_search_errors_are_translated(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.errors["ytsearch10:x"] = OSError(101, "Network is unreachable")
    with pytest.raises(youtube.YoutubeOfflineError) as error:
        youtube.search(token, "x", backend=fake)
    assert "Network is unreachable" in error.value.detail


def test_resolve(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.add(video_info(ID))
    result = youtube.resolve(token, ID, backend=fake)
    assert result == youtube.SearchResult(
        video_id=ID,
        title="Nuvole bianche",
        channel="Ludovico Einaudi",
        duration_s=357.0,
        thumbnail_url=f"https://i.ytimg.com/vi/{ID}/mqdefault.jpg",
        is_live=False,
        url=f"https://www.youtube.com/watch?v={ID}",
    )
    assert fake.calls == [f"extract_info https://www.youtube.com/watch?v={ID} flat=False"]


def test_resolve_returns_live_and_long_videos(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.add(video_info(numbered_id(1), live_status="is_live", duration=None))
    fake.add(video_info(numbered_id(2), duration=defaults.YOUTUBE_MAX_DURATION_S + 1))
    assert youtube.resolve(token, numbered_id(1), backend=fake).is_live
    assert youtube.resolve(token, numbered_id(2), backend=fake).duration_s == 1201.0


def test_resolve_unavailable_video(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    with pytest.raises(youtube.YoutubeUnavailableError) as error:
        youtube.resolve(token, ID, backend=fake)  # the fake says "Video unavailable"
    assert error.value.message_key == youtube.ERROR_UNAVAILABLE


def test_resolve_checks_the_answer(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    fake.videos[ID] = video_info(numbered_id(9))
    with pytest.raises(youtube.YoutubeBrokenError):
        youtube.resolve(token, ID, backend=fake)
    with pytest.raises(ValueError):
        youtube.resolve(token, "not an id", backend=fake)


def test_fetch_thumbnail(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    url = f"https://i.ytimg.com/vi/{ID}/mqdefault.jpg"
    fake.thumbnails[url] = b"\xff\xd8jpeg"
    assert youtube.fetch_thumbnail(token, url, backend=fake) == b"\xff\xd8jpeg"


@pytest.mark.parametrize(
    "url",
    [
        f"http://i.ytimg.com/vi/{ID}/mqdefault.jpg",
        "https://example.org/a.jpg",
        "https://ytimg.com.example.org/a.jpg",
        "file:///C:/Windows/win.ini",
        "",
    ],
)
def test_fetch_thumbnail_only_goes_to_youtube_images(
    url: str, token: ConsentToken, fake: FakeYoutubeBackend
) -> None:
    with pytest.raises(ValueError):
        youtube.fetch_thumbnail(token, url, backend=fake)
    assert fake.calls == []


def test_fetch_thumbnail_errors(token: ConsentToken, fake: FakeYoutubeBackend) -> None:
    url = f"https://i9.ytimg.com/vi/{ID}/mqdefault.jpg"
    fake.thumbnails[url] = bytes(THUMBNAIL_MAX_BYTES + 1)
    with pytest.raises(youtube.YoutubeBrokenError):
        youtube.fetch_thumbnail(token, url, backend=fake)
    fake.errors[url] = TimeoutError("timed out")
    with pytest.raises(youtube.YoutubeOfflineError):
        youtube.fetch_thumbnail(token, url, backend=fake)
