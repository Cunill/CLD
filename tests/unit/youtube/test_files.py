"""C03: safe_target_path, file names valid on Windows that never overwrite anything (contract §15)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from passimaker.youtube import safe_target_path
from passimaker.youtube.files import (
    FALLBACK_NAME,
    MAX_NAME_BYTES,
    MAX_NAME_UNITS,
    MIN_NAME_UNITS,
    WINDOWS_MAX_PATH,
    safe_name,
)

RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in "123456789¹²³"}
FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _valid_on_windows(name: str) -> bool:
    stem = name.split(".")[0].rstrip(" ")
    return (
        bool(name)
        and not FORBIDDEN.search(name)
        and not name.endswith((" ", "."))
        and not name.startswith(" ")
        and stem.upper() not in RESERVED
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Nuvole bianche", "Nuvole bianche.mp3"),
        ("AC/DC: Back In Black (Official Video)", "AC DC Back In Black (Official Video).mp3"),
        ('Què "fem"? <avui> | demà *', "Què fem avui demà.mp3"),
        ("L'estaca — Lluís Llach 🎵", "L'estaca — Lluís Llach 🎵.mp3"),
        ("tab\tand\nnew line", "tab and new line.mp3"),
        ("Final dots...", "Final dots.mp3"),
        ("   spaces   around   ", "spaces around.mp3"),
        ("CON", "_CON.mp3"),
        ("con.txt", "_con.txt.mp3"),
        ("Lpt9", "_Lpt9.mp3"),
        ("COM¹", "_COM¹.mp3"),
        ("Console", "Console.mp3"),
        ("CON song", "CON song.mp3"),
        ("", f"{FALLBACK_NAME}.mp3"),
        ("???", f"{FALLBACK_NAME}.mp3"),
        ("...", f"{FALLBACK_NAME}.mp3"),
    ],
)
def test_titles_become_valid_names(title: str, expected: str, tmp_path: Path) -> None:
    assert safe_target_path(tmp_path, title) == tmp_path / expected


def test_composed_and_decomposed_accents_give_the_same_name(tmp_path: Path) -> None:
    assert safe_target_path(tmp_path, "Lluís") == safe_target_path(tmp_path, "Lluís")


def test_existing_files_are_never_overwritten(tmp_path: Path) -> None:
    first = safe_target_path(tmp_path, "Cançó")
    first.write_bytes(b"1")
    second = safe_target_path(tmp_path, "Cançó")
    assert second == tmp_path / "Cançó (2).mp3"
    second.write_bytes(b"2")
    (tmp_path / "Cançó (3).mp3").mkdir()  # a folder also takes the name
    assert safe_target_path(tmp_path, "Cançó") == tmp_path / "Cançó (4).mp3"
    assert first.read_bytes() == b"1"


def test_a_broken_link_also_takes_the_name(tmp_path: Path) -> None:
    link = tmp_path / "Cançó.mp3"
    try:
        link.symlink_to(tmp_path / "missing.mp3")
    except OSError:
        pytest.skip("symbolic links are not allowed here")
    assert safe_target_path(tmp_path, "Cançó") == tmp_path / "Cançó (2).mp3"


def test_long_titles_are_cut(tmp_path: Path) -> None:
    name = safe_target_path(tmp_path, "a" * 500).name
    assert name == "a" * MAX_NAME_UNITS + ".mp3"


def test_emojis_count_as_two_and_are_never_split() -> None:
    odd = safe_name("x" + "🎵" * 200, 10)
    assert odd == "x" + "🎵" * 4 and _units(odd) == 9


def test_names_also_fit_in_255_bytes(tmp_path: Path) -> None:
    """Linux and network drives count bytes: an emoji is 4 bytes, a CJK character 3."""
    for title in ("🎵" * 200, "音" * 200, "à" * 200):
        path = safe_target_path(tmp_path, title)
        assert len(path.stem.encode()) <= MAX_NAME_BYTES
        path.write_bytes(b"")  # the file system accepts it
        assert len(safe_target_path(tmp_path, title).name.encode()) <= 255


def test_cutting_does_not_leave_a_final_space_or_dot(tmp_path: Path) -> None:
    assert safe_name("abcd. efgh", 6) == "abcd"


def test_deep_folders_get_shorter_names(tmp_path: Path) -> None:
    folder = tmp_path / ("d" * 60) / ("e" * 60)
    path = safe_target_path(folder, "t" * 500)
    longest = path.with_name(path.stem + " (9999).mp3")
    assert _units(str(longest)) <= WINDOWS_MAX_PATH or len(path.stem) == MIN_NAME_UNITS
    assert len(path.stem) < MAX_NAME_UNITS


def test_very_deep_folders_keep_a_minimum(tmp_path: Path) -> None:
    folder = tmp_path / ("d" * 250)
    assert len(safe_target_path(folder, "t" * 500).stem) == MIN_NAME_UNITS


@settings(max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(max_size=300))
def test_any_title_gives_a_valid_free_name(tmp_path: Path, title: str) -> None:
    path = safe_target_path(tmp_path, title)
    assert path.parent == tmp_path and path.suffix == ".mp3"
    assert _valid_on_windows(path.name), path.name
    assert _units(path.stem) <= MAX_NAME_UNITS
    assert len(path.name.encode("utf-8", "surrogatepass")) <= 255
    assert not path.exists()


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(min_size=1, max_size=40), st.integers(min_value=1, max_value=4))
def test_repeated_titles_get_distinct_names(tmp_path: Path, title: str, copies: int) -> None:
    folder = tmp_path / f"run{abs(hash((title, copies)))}"
    folder.mkdir(exist_ok=True)
    for existing in folder.iterdir():
        existing.unlink()
    names: list[Path] = []
    for _ in range(copies):
        path = safe_target_path(folder, title)
        assert path not in names
        path.write_bytes(b"")
        names.append(path)
