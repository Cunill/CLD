"""C02: the yt-dlp spike script (tools/prova_youtube.py), without network."""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "prova_youtube.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prova_youtube", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


prova = _load()


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("intent de connexió a la xarxa")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_importing_the_script_does_not_load_yt_dlp_nor_connect() -> None:
    code = (
        "import socket, sys, importlib.util\n"
        "def refuse(*a, **k): raise SystemExit('connexió')\n"
        "socket.socket.connect = refuse\n"
        "socket.create_connection = refuse\n"
        f"spec = importlib.util.spec_from_file_location('prova_youtube', {str(SCRIPT)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['prova_youtube'] = module\n"
        "spec.loader.exec_module(module)\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in {'yt_dlp', 'yt_dlp_ejs', 'PySide6'}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_proxy_password_is_hidden() -> None:
    assert prova.mask_proxy("http://joan:secret@proxy.estudi:8080") == "http://joan:***@proxy.estudi:8080"
    assert prova.mask_proxy("http://proxy.estudi:8080") == "http://proxy.estudi:8080"


def test_offline_run_writes_the_versions(tmp_path: Path, no_network: None) -> None:
    report = tmp_path / "informe.txt"
    code = prova.main(["--sense-xarxa", "--sense-avis", "--informe", str(report)])
    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert "yt-dlp: 2026.10.21 · yt-dlp-ejs: 0.8.0" in text
    assert "Deno: " in text and "versió: 2." in text
    assert "Scripts de yt-dlp-ejs: core" in text
    assert "Resultat final: CORRECTE" in text


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(b"\x00\x00" * 2 * 48000)


class FakeYdl:
    """Stands in for yt_dlp.YoutubeDL: three search results and a one-second WAV."""

    calls: list[dict[str, Any]] = []  # noqa: RUF012 (shared on purpose: the test reads it)

    def __init__(self, options: dict[str, Any], fail_download: bool = False) -> None:
        self.options = options
        self.fail_download = fail_download
        FakeYdl.calls.append(options)

    def __enter__(self) -> FakeYdl:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool) -> dict[str, Any]:
        logger = self.options["logger"]
        if url.startswith("ytsearch"):
            assert not download
            return {"entries": [{"id": f"id{i}", "title": f"Títol {i}", "duration": 60} for i in range(3)]}
        if self.fail_download:
            logger.warning("No supported JavaScript runtime could be found.")
            raise RuntimeError("ERROR: [youtube] aqz-KE-bpKQ: Sign in to confirm you're not a bot")
        logger.debug("[jsc:deno] Running deno: deno run -")
        path = Path(self.options["outtmpl"].replace("%(id)s", "aqz-KE-bpKQ").replace("%(ext)s", "wav"))
        _write_wav(path)
        return {"title": "Big Buck Bunny", "ext": "wav", "requested_downloads": [{"filepath": str(path)}]}


def test_full_run_with_a_fake_yt_dlp(tmp_path: Path, no_network: None) -> None:
    FakeYdl.calls.clear()
    report = tmp_path / "informe.txt"

    def factory(options: dict[str, Any]) -> FakeYdl:
        return FakeYdl(options, fail_download=not options["js_runtimes"])

    code = prova.main(["--sense-avis", "--informe", str(report)], ydl_factory=factory)
    text = report.read_text(encoding="utf-8")
    assert code == 0  # the Deno variant decides; the one without JavaScript only informs
    assert "Amb Deno: CORRECTE" in text
    assert "Sense entorn JavaScript: HA FALLAT" in text
    assert "Sign in to confirm you're not a bot" in text and "Traceback" in text
    assert "Deno executat 1 vegades" in text
    assert "1.0 s · àudio: True · 48000 Hz · 2 canals" in text
    deno_options = [c for c in FakeYdl.calls if c["js_runtimes"]]
    assert deno_options and all(Path(c["js_runtimes"]["deno"]["path"]).is_file() for c in deno_options)
    for options in FakeYdl.calls:
        assert (
            options["postprocessors"] == [] and options["fixup"] == "never" and options["cachedir"] is False
        )


def test_failed_search_is_reported_and_fails_the_run(tmp_path: Path, no_network: None) -> None:
    class BrokenYdl(FakeYdl):
        def extract_info(self, url: str, download: bool) -> dict[str, Any]:
            raise OSError("Tunnel connection failed: 403 Forbidden")

    report = tmp_path / "informe.txt"
    code = prova.main(["--sense-avis", "--informe", str(report)], ydl_factory=BrokenYdl)
    text = report.read_text(encoding="utf-8")
    assert code == 1
    assert text.count("Tunnel connection failed: 403 Forbidden") >= 4  # two steps, two variants
    assert "Resultat final: HA FALLAT" in text


def test_report_falls_back_to_the_temporary_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prova.tempfile, "gettempdir", lambda: str(tmp_path))
    written = prova.write_report(prova.Report(["hola"]), tmp_path / "no_hi_és" / "informe.txt")
    assert written == tmp_path / "informe.txt"
    assert written.read_text(encoding="utf-8") == "hola\n"
