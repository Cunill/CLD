"""B0: architecture rules from CLAUDE.md that can be checked automatically."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "passimaker"
QT_ALLOWED = {"ui", "preview"}
CORE_MODULES = [
    "passimaker.common",
    "passimaker.model",
    "passimaker.importer",
    "passimaker.images",
    "passimaker.thumbs",
    "passimaker.timeline",
    "passimaker.motion",
    "passimaker.render",
    "passimaker.ffmpeg",
    "passimaker.audio",
    "passimaker.export",
    "passimaker.projectio",
    "passimaker.i18n",
    "passimaker.cli",
    "passimaker.youtube",
    "passimaker.recorder",
]
NETWORK_MODULES = {"yt_dlp", "urllib.request", "http.client", "socket"}
"""Only passimaker.youtube may import these (decision 0012: no network anywhere else)."""


def test_core_does_not_import_qt() -> None:
    code = (
        "import sys\n"
        + "".join(f"import {m}\n" for m in CORE_MODULES)
        + "bad = [m for m in sys.modules if m.startswith('PySide6') or m.startswith('shiboken')]\n"
        + "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "", f"El nucli importa Qt: {out.stdout}"


def test_only_ui_and_preview_mention_pyside() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "PySide6" in path.read_text(encoding="utf-8") and path.relative_to(SRC).parts[0] not in QT_ALLOWED
    ]
    assert offenders == []


def test_only_ffmpeg_module_runs_subprocesses() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "subprocess" in path.read_text(encoding="utf-8") and path.relative_to(SRC).parts[0] != "ffmpeg"
    ]
    assert offenders == []


def test_qt_modules_import() -> None:
    import passimaker.preview
    import passimaker.ui.app

    assert passimaker.preview.PREVIEW_MAX_SIZE == (960, 540)
    assert callable(passimaker.ui.app.main)


def _imported_modules(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _is_network(name: str) -> bool:
    return any(name == bad or name.startswith(bad + ".") for bad in NETWORK_MODULES)


def test_only_youtube_module_imports_network_modules() -> None:
    offenders = [
        f"{path.relative_to(SRC)}: {name}"
        for path in SRC.rglob("*.py")
        if path.relative_to(SRC).parts[0] != "youtube"
        for name in sorted(_imported_modules(path.read_text(encoding="utf-8")))
        if _is_network(name)
    ]
    assert offenders == []


def test_the_network_check_sees_every_import_form() -> None:
    """Guards the test above: it would pass trivially if the import parser missed something."""
    sample = (
        "import socket\nimport urllib.request as r\nfrom http import client\n"
        + "from yt_dlp import YoutubeDL\n"
    )
    found = {name for name in _imported_modules(sample) if _is_network(name)}
    assert not _is_network("urllib.parse")
    assert {"socket", "urllib.request", "http.client", "yt_dlp"} <= found


def test_importing_the_program_does_not_load_yt_dlp() -> None:
    code = (
        "import sys\n"
        + "".join(f"import {m}\n" for m in CORE_MODULES)
        + "import passimaker.ui.app\n"
        + "print('yt_dlp' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_recorder_imports_neither_qt_nor_network_modules() -> None:
    """Decision 0013: recording works offline and without Qt (the interface is block C10)."""
    files = sorted((SRC / "recorder").rglob("*.py"))
    assert files
    offenders = [
        f"{path.relative_to(SRC)}: {name}"
        for path in files
        for name in sorted(_imported_modules(path.read_text(encoding="utf-8")))
        if _is_network(name) or name.split(".")[0] in {"PySide6", "shiboken6"}
    ]
    assert offenders == []
