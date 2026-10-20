"""B0: architecture rules from CLAUDE.md that can be checked automatically."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "passi"
QT_ALLOWED = {"ui", "preview"}
CORE_MODULES = [
    "passi.common",
    "passi.model",
    "passi.importer",
    "passi.images",
    "passi.thumbs",
    "passi.timeline",
    "passi.motion",
    "passi.render",
    "passi.ffmpeg",
    "passi.audio",
    "passi.export",
    "passi.projectio",
    "passi.i18n",
    "passi.cli",
]


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
    import passi.preview
    import passi.ui.app

    assert passi.preview.PREVIEW_MAX_SIZE == (960, 540)
    assert callable(passi.ui.app.main)
