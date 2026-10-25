"""C08: the sound-recording spike script (tools/prova_gravacio.py), with a fake sound system."""

from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "prova_gravacio.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prova_gravacio", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


prova = _load()
RATE = prova.SAMPLE_RATE


class FakeStream:
    """Half a second of silence, then a 440 Hz tone at -6 dBFS on the left and -12 dBFS on the right."""

    def __init__(self, backend: FakeBackend, channels: int) -> None:
        self.backend = backend
        self.channels = channels
        self.position = 0

    def read(self, frames: int) -> tuple[np.ndarray, int]:
        self.backend.reads += 1
        if self.backend.read_delay_s:
            time.sleep(self.backend.read_delay_s)
        if self.backend.lose_after is not None and self.backend.reads > self.backend.lose_after:
            raise RuntimeError("Error 0x88890004")
        t = (self.position + np.arange(frames)) / RATE
        tone = np.sin(2 * np.pi * 440 * t)[:, None] * np.array([0.5, 0.25][: self.channels])
        tone[t < 0.5] = 0
        self.position += frames
        lost = 1 if self.backend.reads == 3 and self.backend.discontinuity else 0
        return tone.astype(np.float32), lost


class FakeBackend:
    """A loopback output and a microphone; capture needs COM initialised in its own thread."""

    def __init__(self) -> None:
        self.local = threading.local()
        self.reads = 0
        self.read_delay_s = 0.0
        self.lose_after: int | None = None
        self.discontinuity = True
        self.default_output = "{altaveus}"
        self.outputs = ["{altaveus}", "{bluetooth}"]
        self.opened: list[tuple[str, int, str]] = []

    def describe(self) -> list[str]:
        return ["COM al fil principal (com Qt, STA): fals"]

    def sources(self) -> list[object]:
        return [
            prova.Source(0, "{altaveus}", "Altaveus (Realtek)", True, 2, 48000, True),
            prova.Source(1, "{bluetooth}", "Auriculars (Bluetooth)", True, 2, 44100, False),
            prova.Source(2, "{micro}", "Micròfon (Realtek)", False, 1, 44100, True),
        ]

    def output_ids(self) -> tuple[str | None, list[str]]:
        return self.default_output, list(self.outputs)

    @contextlib.contextmanager
    def open(self, source: object, channels: int) -> Iterator[FakeStream]:
        if not getattr(self.local, "com", False):
            raise RuntimeError("Error 0x800401f0")
        self.opened.append((source.id, channels, threading.current_thread().name))  # type: ignore[attr-defined]
        yield FakeStream(self, channels)

    def init_thread(self) -> str:
        self.local.com = True
        return "S_OK"

    def end_thread(self) -> None:
        self.local.com = False


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prova, "COM_CHECK_S", 0.2)


def _run(tmp_path: Path, backend: FakeBackend, *args: str) -> tuple[int, str]:
    report = tmp_path / "informe.txt"
    code = prova.main([*args, "--sense-avis", "--informe", str(report)], backend_factory=lambda: backend)
    return code, report.read_text(encoding="utf-8")


def test_importing_the_script_opens_no_device() -> None:
    code = (
        "import sys, importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('prova_gravacio', {str(SCRIPT)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['prova_gravacio'] = module\n"
        "spec.loader.exec_module(module)\n"
        "names = {'soundcard', 'sounddevice', 'PySide6'}\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in names))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_without_device_only_the_versions(tmp_path: Path) -> None:
    def refuse() -> FakeBackend:
        raise AssertionError("no s'ha d'obrir el sistema de so")

    report = tmp_path / "informe.txt"
    code = prova.main(
        ["--sense-dispositiu", "--sense-avis", "--informe", str(report)], backend_factory=refuse
    )
    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert "soundcard: 0.4.6" in text and "FFmpeg: " in text
    assert "Resultat final: CORRECTE" in text


def test_list_only(tmp_path: Path) -> None:
    backend = FakeBackend()
    code, text = _run(tmp_path, backend, "--llista")
    assert code == 0
    assert "[0] So de l'ordinador: Altaveus (Realtek) · 2 canals · 48000 Hz · PER DEFECTE" in text
    assert "[2] Entrada (micròfon o línia): Micròfon (Realtek) · 1 canals · 44100 Hz" in text
    assert backend.opened == [] and "Gravació" not in text


def test_full_run_with_tones_and_silence(tmp_path: Path) -> None:
    backend = FakeBackend()
    code, text = _run(tmp_path, backend, "--durada", "1.5")
    assert code == 0, text
    assert "sense inicialitzar COM al fil: ERROR" in text and "CO_E_NOTINITIALIZED" in text
    assert "amb CoInitializeEx (MTA) al fil: correcte" in text
    assert "Rebut: 1.50 s" in text
    assert "Canal E: nivell (RMS)  -10.8 dBFS · pic   -6.0 dBFS" in text
    assert "Canal D: nivell (RMS)  -16.8 dBFS · pic  -12.0 dBFS" in text
    assert "Primer so (> -60 dBFS): 0.50 s" in text
    assert "Blocs tot zeros (silenci; en loopback, també quan Windows no envia res): 5" in text
    assert "Discontinuïtats de WASAPI (dades perdudes de debò): 1" in text
    assert "probe del WAV: 1.50 s · àudio: True · 48000 Hz · 2 canals" in text
    assert "MP3 192 kbps" in text and "48000 Hz · 2 canals" in text
    assert "Resultat final: CORRECTE" in text
    assert all(name == "prova-gravacio" for _, _, name in backend.opened)
    assert not list(Path(prova.tempfile.gettempdir()).glob(f"{prova.WAV_PREFIX}*/*.wav"))


def test_microphone_by_number_and_kept_files(tmp_path: Path) -> None:
    backend = FakeBackend()
    code, text = _run(tmp_path, backend, "--origen", "2", "--durada", "0.6", "--conservar")
    assert code == 0, text
    assert backend.opened[-1][:2] == ("{micro}", 1)
    assert "Canal 1: nivell" in text and "probe del WAV: 0.60 s · àudio: True · 48000 Hz · 1 canals" in text
    kept = Path(text.split("Carpeta conservada: ")[1].splitlines()[0])
    assert sorted(p.suffix for p in kept.iterdir()) == [".mp3", ".wav"]
    prova.shutil.rmtree(kept)


def test_only_silence_is_reported(tmp_path: Path) -> None:
    backend = FakeBackend()
    code, text = _run(tmp_path, backend, "--durada", "0.4")
    assert code == 0
    assert "Primer so (> -60 dBFS): cap: TOT ÉS SILENCI" in text
    assert "pic   -inf dBFS" in text


def test_lost_device_and_default_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prova, "DEVICE_POLL_S", 0.01)
    backend = FakeBackend()
    backend.read_delay_s = 0.02
    original = backend.output_ids

    def switching() -> tuple[str | None, list[str]]:
        if backend.reads > 15 and backend.lose_after is None:  # after the COM check and some recording
            backend.default_output, backend.outputs = "{bluetooth}", ["{bluetooth}"]
            backend.lose_after = backend.reads + 2
        return original()

    backend.output_ids = switching  # type: ignore[method-assign]
    code, text = _run(tmp_path, backend, "--durada", "5")
    assert code == 1
    assert "la sortida per defecte ha canviat: {altaveus} → {bluetooth}" in text
    assert "la sortida que es grava ja no hi és (Altaveus (Realtek))" in text
    assert "ERROR de la captura: RuntimeError: Error 0x88890004 (AUDCLNT_E_DEVICE_INVALIDATED" in text
    assert "Traceback" in text and "Resultat final: HA FALLAT" in text


def test_wrong_source_number(tmp_path: Path) -> None:
    code, text = _run(tmp_path, FakeBackend(), "--origen", "7")
    assert code == 1
    assert "No hi ha l'origen 7: n'hi ha de 0 a 2." in text


def test_float_wav_is_read_by_ffmpeg(tmp_path: Path) -> None:
    from passimaker.ffmpeg import decode_audio

    wav = prova.FloatWavWriter(tmp_path / "a.wav", 48000, 2)
    block = np.full((4800, 2), 0.25, dtype=np.float32)
    wav.write(block)
    wav.write(-block)
    wav.close()
    pcm = decode_audio(wav.path, tmp_path / "pcm.f32", 0.0, None)
    assert pcm.frames == 9600


def test_report_falls_back_to_the_temporary_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prova.tempfile, "gettempdir", lambda: str(tmp_path))
    written = prova.write_report(prova.Report(["hola"]), tmp_path / "no_hi_és" / "informe.txt")
    assert written == tmp_path / "informe.txt"


def test_each_run_is_added_to_the_report(tmp_path: Path) -> None:
    _run(tmp_path, FakeBackend(), "--llista")
    _code, text = _run(tmp_path, FakeBackend(), "--origen", "9")
    assert text.count("Prova de gravació del so de PassiMaker") == 2
    assert text.index("Opcions: --llista") < text.index("Opcions: --origen 9")
