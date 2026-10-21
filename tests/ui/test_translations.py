"""Rule 8: no visible text outside tr(), and the catalogue covers every error of the core.

The first test reads the source of passimaker.ui and checks that no plain string literal is
given to a Qt call that shows text. The second checks that every message key the core can raise
has Catalan text in passimaker.i18n (decision 0007).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from passimaker import projectio
from passimaker.export import pipeline
from passimaker.ffmpeg import types as ffmpeg_types
from passimaker.i18n import MESSAGES, message
from passimaker.importer import ImportFailure
from passimaker.ui.translations import LANGUAGE

pytestmark = pytest.mark.ui

UI = Path(__file__).resolve().parents[2] / "src" / "passimaker" / "ui"

TEXT_CALLS = frozenset(
    {
        # Setters that put text on screen.
        "setText",
        "setWindowTitle",
        "setToolTip",
        "setStatusTip",
        "setWhatsThis",
        "setPlaceholderText",
        "setTitle",
        "setLabelText",
        "setSuffix",
        "setPrefix",
        "setInformativeText",
        "setItemText",
        "setTabText",
        "setAccessibleName",
        "addItem",
        "addTab",
        "insertItem",
        # Widgets and actions built with their text.
        "QLabel",
        "QPushButton",
        "QAction",
        "QToolBar",
        "QGroupBox",
        "QCheckBox",
        "QRadioButton",
        "QMenu",
        "addMenu",
        "addAction",
        # Standard dialogs.
        "question",
        "information",
        "warning",
        "critical",
        "about",
        "getOpenFileNames",
        "getExistingDirectory",
        "getSaveFileName",
    }
)
"""Qt calls whose string arguments end up in front of the user."""


def _called_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _bare_texts(call: ast.Call) -> list[str]:
    """String literals given straight to the call (not through tr(), a variable or an f-string)."""
    found: list[str] = []
    for argument in [*call.args, *(keyword.value for keyword in call.keywords)]:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value:
            found.append(argument.value)
    return found


def test_no_visible_text_outside_tr() -> None:
    offenders: list[str] = []
    for path in sorted(UI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _called_name(node) not in TEXT_CALLS:
                continue
            for text in _bare_texts(node):
                offenders.append(f"{path.name}:{node.lineno} {_called_name(node)}({text!r})")
    assert offenders == [], "textos visibles fora de tr(): " + "; ".join(offenders)


def test_the_interface_calls_tr_somewhere() -> None:
    """Guards the test above: it would pass trivially if nothing had text at all."""
    sources = "\n".join(path.read_text(encoding="utf-8") for path in UI.rglob("*.py"))
    assert sources.count("self.tr(") > 30


def test_the_catalogue_covers_the_errors_of_the_core() -> None:
    keys: set[str] = set()
    for module in (ffmpeg_types, pipeline, projectio):
        keys.update(
            value
            for name, value in vars(module).items()
            if name.startswith("ERROR_") and isinstance(value, str)
        )
    assert keys, "no s'ha trobat cap clau d'error"
    assert sorted(key for key in keys if key not in MESSAGES) == []


def test_the_catalogue_covers_the_import_failures() -> None:
    for failure in ImportFailure:
        key = f"import.{failure.value}"
        assert key in MESSAGES, key
        assert message(key) != key


def test_every_message_is_in_catalan_and_not_a_key() -> None:
    for key, text in MESSAGES.items():
        assert text and text != key
        assert text[0].isupper() or text[0] in "¿¡", key
        assert text.endswith((".", "?", "!")), key


def test_the_language_is_catalan() -> None:
    assert LANGUAGE == "ca"
