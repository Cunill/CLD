"""C08 spike: can a PyInstaller ZIP record the computer's sound on Windows? (docs/sessions/C08.md)

ProvaGravacio.exe (packaging/ProvaGravacio.spec, no console) lists every source (outputs through WASAPI
loopback, and inputs: microphone, line in), records the default output (or --origen N) for 20 s to a
temporary float32 WAV while it measures the level and peaks per channel, counts lost blocks and watches
the default output, then checks the WAV with passimaker.ffmpeg.probe and converts it with
passimaker.ffmpeg.convert_to_mp3. Everything is added at the end of a text report next to the executable.

Capture goes through soundcard (approved by the user on 25/10/2026: sounddevice's PortAudio 19.7.0 has no
loopback). Two things the program will depend on (block C09) are measured too:
- silence or lost blocks: in loopback, WASAPI sends no packets while nothing plays and soundcard fills the
  gap with zeros; data that is really lost comes with WASAPI's "data discontinuity" flag, and shows as
  fewer samples than the clock says;
- COM in the capture thread: soundcard initialises COM only in the thread that imports it. Qt makes the
  program's main thread single-threaded (STA), so this script does the same before importing soundcard,
  and then captures in another thread, first without initialising COM there and then initialising it.

Not part of the program: passimaker.recorder (block C09) is the real implementation. Importing this module
opens no sound device and does not import soundcard.

  ProvaGravacio.exe [--durada S] [--origen N] [--llista] [--sense-dispositiu] [--conservar]
                    [--informe FITXER] [--sense-avis]
  uv run python tools/prova_gravacio.py [same options]
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib
import importlib.metadata
import os
import platform
import shutil
import struct
import sys
import tempfile
import threading
import time
import traceback
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Protocol

import numpy as np

REPORT_NAME = "informe_prova_gravacio.txt"
SAMPLE_RATE = 48000
"""Asked of WASAPI, which converts from the device's own rate (soundcard turns on AUTOCONVERTPCM)."""
MAX_CHANNELS = 2
"""A 5.1 output is recorded as its stereo mix, as the program will (PLA_GRAVACIO §2.4)."""
BLOCK_S = 0.1
DEFAULT_DURATION_S = 20.0
COM_CHECK_S = 1.0
DEVICE_POLL_S = 1.0
LATE_FACTOR = 3.0
"""A block that takes more than this many block lengths to arrive counts as late."""
SILENCE_DBFS = -60.0
MP3_KBPS = 192
WAV_PREFIX = "passimaker_prova_gravacio_"

# HRESULTs that soundcard reports as "Error 0x…" (um/audioclient.h, winerror.h).
KNOWN_ERRORS = {
    "0x88890004": "AUDCLNT_E_DEVICE_INVALIDATED: l'origen ha desaparegut (desconnectat o canviat)",
    "0x8889000a": "AUDCLNT_E_DEVICE_IN_USE: una altra aplicació la fa servir en mode exclusiu",
    "0x800401f0": "CO_E_NOTINITIALIZED: COM no està inicialitzat en aquest fil",
    "0x80070005": "E_ACCESSDENIED: Windows ha denegat l'accés (permís del micròfon?)",
}


@dataclass(frozen=True)
class Source:
    index: int
    id: str
    name: str
    loopback: bool
    channels: int
    sample_rate: int | None
    is_default: bool

    def label(self) -> str:
        kind = "So de l'ordinador" if self.loopback else "Entrada (micròfon o línia)"
        rate = f"{self.sample_rate} Hz" if self.sample_rate else "freqüència desconeguda"
        default = " · PER DEFECTE" if self.is_default else ""
        return f"[{self.index}] {kind}: {self.name} · {self.channels} canals · {rate}{default}"


class Stream(Protocol):
    def read(self, frames: int) -> tuple[np.ndarray, int]:
        """`frames` × channels float32, and how many data discontinuities WASAPI reported meanwhile."""
        ...


class Backend(Protocol):
    """What the script needs from the sound system (soundcard on Windows; the tests pass a fake)."""

    def describe(self) -> list[str]: ...

    def sources(self) -> list[Source]:
        """Outputs (loopback) first, the default one first of all; then the inputs."""
        ...

    def output_ids(self) -> tuple[str | None, list[str]]:
        """The default output and every active output, to see changes while recording."""
        ...

    def open(self, source: Source, channels: int) -> contextlib.AbstractContextManager[Stream]: ...

    def init_thread(self) -> str:
        """Initialises COM in the calling thread (multithreaded apartment); returns what happened."""
        ...

    def end_thread(self) -> None: ...


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)

    def add(self, text: str = "") -> None:
        self.lines.extend(text.splitlines() or [""])

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def explain(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}"
    for code, meaning in KNOWN_ERRORS.items():
        if code in str(error).lower():
            text += f" ({meaning})"
    return text


# --- soundcard (Windows) ------------------------------------------------------------------------------


class SoundcardBackend:
    """soundcard's WASAPI backend, with the main thread made STA first, as Qt does."""

    def __init__(self) -> None:
        self.main_com = _init_com(apartment_threaded=True)
        self.sc: Any = importlib.import_module("soundcard")
        self._mf: Any = importlib.import_module("soundcard.mediafoundation")
        self._thread_com = threading.local()

    def describe(self) -> list[str]:
        loaded = getattr(self._mf, "_com", None)
        owns = getattr(loaded, "com_loaded", None)
        return [
            f"COM al fil principal (com Qt, STA): {self.main_com}",
            f"soundcard ha inicialitzat COM en importar-se: {'sí' if owns else 'no (ja hi era)'}",
        ]

    def sources(self) -> list[Source]:
        sc = self.sc
        default_out = sc.default_speaker().id
        try:
            default_in = sc.default_microphone().id
        except Exception:
            default_in = None
        speakers = sorted(sc.all_speakers(), key=lambda s: s.id != default_out)
        found: list[Source] = []
        for speaker in speakers:
            mic = sc.get_microphone(speaker.id, include_loopback=True)
            found.append(self._source(len(found), mic, True, speaker.id == default_out))
        for mic in sorted(sc.all_microphones(), key=lambda m: m.id != default_in):
            found.append(self._source(len(found), mic, False, mic.id == default_in))
        return found

    def _source(self, index: int, mic: Any, loopback: bool, is_default: bool) -> Source:
        return Source(index, mic.id, mic.name, loopback, int(mic.channels), self._mix_rate(mic), is_default)

    def _mix_rate(self, mic: Any) -> int | None:
        """The rate Windows mixes at (soundcard does not tell it): IAudioClient::GetMixFormat."""
        mf = self._mf
        try:
            client = mic._audio_client()
            fmt = mf._ffi.new("WAVEFORMATEXTENSIBLE**")
            mf._com.check_error(client[0][0].lpVtbl.GetMixFormat(client[0], fmt))
            rate = int(fmt[0][0].Format.nSamplesPerSec)
            mf._ole32.CoTaskMemFree(fmt[0])
            mf._com.release(client)
            return rate
        except Exception:
            return None

    def output_ids(self) -> tuple[str | None, list[str]]:
        try:
            default = self.sc.default_speaker().id
        except Exception:
            default = None
        return default, [s.id for s in self.sc.all_speakers()]

    @contextlib.contextmanager
    def open(self, source: Source, channels: int) -> Iterator[Stream]:
        mic = self.sc.get_microphone(source.id, include_loopback=source.loopback)
        with mic.recorder(samplerate=SAMPLE_RATE, channels=channels) as recorder:
            yield _SoundcardStream(recorder)

    def init_thread(self) -> str:
        result = _init_com(apartment_threaded=False)
        self._thread_com.initialised = result.startswith("S_")
        return result

    def end_thread(self) -> None:
        if getattr(self._thread_com, "initialised", False) and sys.platform == "win32":
            import ctypes

            ctypes.windll.ole32.CoUninitialize()


class _SoundcardStream:
    def __init__(self, recorder: Any) -> None:
        self._recorder = recorder

    def read(self, frames: int) -> tuple[np.ndarray, int]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            data = self._recorder.record(numframes=frames)
        lost = sum("discontinuity" in str(w.message) for w in caught)
        return np.asarray(data, dtype=np.float32), lost


def _init_com(apartment_threaded: bool) -> str:
    if sys.platform != "win32":
        return "no és Windows"
    import ctypes

    hr = ctypes.windll.ole32.CoInitializeEx(None, 0x2 if apartment_threaded else 0x0) & 0xFFFFFFFF
    names = {0: "S_OK", 1: "S_FALSE (ja inicialitzat)", 0x80010106: "RPC_E_CHANGED_MODE (un altre model)"}
    return names.get(hr, f"0x{hr:08x}")


# --- recording ----------------------------------------------------------------------------------------


class FloatWavWriter:
    """32-bit float WAV written as it records (the WAV the program will keep in the temporary folder)."""

    def __init__(self, path: Path, rate: int, channels: int) -> None:
        self.path = path
        self.rate = rate
        self.channels = channels
        self.frames = 0
        self._file: BinaryIO = path.open("wb")
        self._file.write(self._header())

    def _header(self) -> bytes:
        data_bytes = self.frames * self.channels * 4
        fmt = struct.pack(
            "<HHIIHHH", 3, self.channels, self.rate, self.rate * self.channels * 4, self.channels * 4, 32, 0
        )
        return (
            b"RIFF"
            + struct.pack("<I", 4 + 8 + len(fmt) + 8 + 4 + 8 + data_bytes)
            + b"WAVE"
            + b"fmt "
            + struct.pack("<I", len(fmt))
            + fmt
            + b"fact"
            + struct.pack("<II", 4, self.frames)
            + b"data"
            + struct.pack("<I", data_bytes)
        )

    def write(self, block: np.ndarray) -> None:
        self._file.write(np.ascontiguousarray(block, dtype="<f4").tobytes())
        self.frames += block.shape[0]

    def close(self) -> None:
        self._file.seek(0)
        self._file.write(self._header())
        self._file.close()


@dataclass
class Capture:
    """What the capture thread measured (read by the main thread once it has finished)."""

    channels: int
    frames: int = 0
    blocks: int = 0
    zero_blocks: int = 0
    longest_zero_run_s: float = 0.0
    discontinuities: int = 0
    late_blocks: int = 0
    longest_wait_s: float = 0.0
    peak: np.ndarray = field(default_factory=lambda: np.zeros(0))
    sum_squares: np.ndarray = field(default_factory=lambda: np.zeros(0))
    first_sound_s: float | None = None
    wall_s: float = 0.0
    com: str = ""
    error: str | None = None
    error_trace: str = ""
    _zero_run: float = 0.0

    def add(self, block: np.ndarray, lost: int, wait_s: float) -> None:
        if self.peak.size == 0:
            self.peak = np.zeros(self.channels)
            self.sum_squares = np.zeros(self.channels)
        frames = block.shape[0]
        start_s = self.frames / SAMPLE_RATE
        self.frames += frames
        self.blocks += 1
        self.discontinuities += lost
        self.longest_wait_s = max(self.longest_wait_s, wait_s)
        if wait_s > LATE_FACTOR * BLOCK_S:
            self.late_blocks += 1
        if frames:
            self.peak = np.maximum(self.peak, np.abs(block).max(axis=0))
            self.sum_squares += np.square(block, dtype=np.float64).sum(axis=0)
        if not np.any(block):
            self.zero_blocks += 1
            self._zero_run += frames / SAMPLE_RATE
            self.longest_zero_run_s = max(self.longest_zero_run_s, self._zero_run)
        else:
            self._zero_run = 0.0
            if self.first_sound_s is None and np.abs(block).max() > _from_dbfs(SILENCE_DBFS):
                self.first_sound_s = start_s

    @property
    def seconds(self) -> float:
        return self.frames / SAMPLE_RATE

    def rms_dbfs(self) -> list[float]:
        if not self.frames:
            return [float("-inf")] * self.channels
        return [_dbfs(float(np.sqrt(s / self.frames))) for s in self.sum_squares]

    def peak_dbfs(self) -> list[float]:
        return [_dbfs(float(p)) for p in self.peak] if self.peak.size else [float("-inf")] * self.channels


def _dbfs(value: float) -> float:
    return 20 * float(np.log10(value)) if value > 0 else float("-inf")


def _from_dbfs(db: float) -> float:
    return float(10 ** (db / 20))


def capture(
    backend: Backend,
    source: Source,
    seconds: float,
    init_com: bool,
    wav: FloatWavWriter | None,
    stop: threading.Event,
) -> Capture:
    """Runs in its own thread, as the program's recorder will."""
    channels = min(source.channels, MAX_CHANNELS)
    result = Capture(channels)
    block = round(BLOCK_S * SAMPLE_RATE)
    started = time.perf_counter()
    try:
        result.com = backend.init_thread() if init_com else "sense inicialitzar"
        with backend.open(source, channels) as stream:
            started = time.perf_counter()
            while result.seconds < seconds and not stop.is_set():
                asked = time.perf_counter()
                data, lost = stream.read(block)
                result.add(data, lost, time.perf_counter() - asked)
                if wav is not None:
                    wav.write(data)
    except Exception as error:
        result.error = explain(error)
        result.error_trace = traceback.format_exc()
    finally:
        result.wall_s = time.perf_counter() - started
        if init_com:
            backend.end_thread()
    return result


def run_in_thread(target: Callable[[], Capture], watch: Callable[[float], None] | None = None) -> Capture:
    """Runs the capture in another thread; meanwhile `watch(seconds)` is called every DEVICE_POLL_S."""
    out: list[Capture] = []
    thread = threading.Thread(target=lambda: out.append(target()), name="prova-gravacio", daemon=True)
    started = time.perf_counter()
    thread.start()
    while thread.is_alive():
        thread.join(DEVICE_POLL_S)
        if watch is not None and thread.is_alive():
            watch(time.perf_counter() - started)
    return out[0]


def com_check(report: Report, backend: Backend, source: Source) -> bool:
    """1 s in another thread without initialising COM there, and 1 s initialising it."""
    report.add()
    report.add("=== COM al fil de captura ===")
    ok = False
    for init in (False, True):
        result = run_in_thread(
            lambda init=init: capture(backend, source, COM_CHECK_S, init, None, threading.Event())
        )
        label = "amb CoInitializeEx (MTA) al fil" if init else "sense inicialitzar COM al fil"
        if result.error is None:
            report.add(f"  {label}: correcte ({result.seconds:.1f} s rebuts) · COM: {result.com}")
            ok = ok or init
        else:
            report.add(f"  {label}: ERROR · COM: {result.com} · {result.error}")
    return ok


@dataclass
class DeviceWatch:
    backend: Backend
    recorded: Source
    report: Report
    first_default: str | None = None
    events: list[str] = field(default_factory=list)
    errors: int = 0

    def __post_init__(self) -> None:
        self.first_default, _ = self.backend.output_ids()
        self._last_default = self.first_default
        self._gone = False

    def __call__(self, at_s: float) -> None:
        try:
            default, outputs = self.backend.output_ids()
        except Exception as error:
            self.errors += 1
            if self.errors == 1:
                self.events.append(f"{at_s:5.1f} s · no s'han pogut llegir les sortides: {explain(error)}")
            return
        if default != self._last_default:
            self.events.append(
                f"{at_s:5.1f} s · la sortida per defecte ha canviat: {self._last_default} → {default}"
            )
            self._last_default = default
        if self.recorded.loopback and not self._gone and self.recorded.id not in outputs:
            self.events.append(f"{at_s:5.1f} s · la sortida que es grava ja no hi és ({self.recorded.name})")
            self._gone = True


def record(report: Report, backend: Backend, source: Source, seconds: float, work: Path) -> bool:
    report.add()
    report.add(f"=== Gravació de {seconds:g} s: {source.name} ===")
    channels = min(source.channels, MAX_CHANNELS)
    wav = FloatWavWriter(work / f"{WAV_PREFIX}{os.getpid()}.wav", SAMPLE_RATE, channels)
    report.add(f"  WAV temporal: {wav.path} · {SAMPLE_RATE} Hz · {channels} canals · float32")
    watch = DeviceWatch(backend, source, report)
    stop = threading.Event()
    try:
        result = run_in_thread(lambda: capture(backend, source, seconds, True, wav, stop), watch)
    finally:
        wav.close()
    report.add(f"  COM al fil de captura: {result.com}")
    report.add(
        f"  Rebut: {result.seconds:.2f} s en {result.wall_s:.2f} s de rellotge · {result.blocks} blocs de "
        f"{BLOCK_S:g} s · WAV: {wav.path.stat().st_size / 1e6:.1f} MB"
    )
    names = ["E", "D"] if channels == 2 else [str(c + 1) for c in range(channels)]
    for name, rms, peak in zip(names, result.rms_dbfs(), result.peak_dbfs(), strict=True):
        report.add(f"  Canal {name}: nivell (RMS) {rms:6.1f} dBFS · pic {peak:6.1f} dBFS")
    report.add(
        "  Primer so (> "
        f"{SILENCE_DBFS:g} dBFS): "
        + (f"{result.first_sound_s:.2f} s" if result.first_sound_s is not None else "cap: TOT ÉS SILENCI")
    )
    report.add("  -- Silenci o blocs perduts")
    report.add(
        f"  Blocs tot zeros (silenci; en loopback, també quan Windows no envia res): {result.zero_blocks} · "
        f"tram més llarg: {result.longest_zero_run_s:.1f} s"
    )
    report.add(f"  Discontinuïtats de WASAPI (dades perdudes de debò): {result.discontinuities}")
    drift = result.seconds - result.wall_s
    report.add(f"  Mostres rebudes − rellotge: {drift:+.2f} s (negatiu: falten mostres)")
    report.add(
        f"  Blocs que han trigat més de {LATE_FACTOR * BLOCK_S:g} s: {result.late_blocks} · "
        f"espera més llarga: {result.longest_wait_s:.2f} s"
    )
    report.add("  -- Canvis de dispositiu")
    report.add(f"  Sortida per defecte en començar: {watch.first_default}")
    for event in watch.events or ["cap"]:
        report.add(f"  {event}")
    if result.error is not None:
        report.add(f"  ERROR de la captura: {result.error}")
        report.add(result.error_trace)
        return False
    return check_files(report, wav.path, work)


def check_files(report: Report, wav: Path, work: Path) -> bool:
    from passimaker.ffmpeg import Mp3Tags, convert_to_mp3, probe

    try:
        media = probe(wav)
        report.add(
            f"  probe del WAV: {media.duration_s:.2f} s · àudio: {media.has_audio} · "
            f"{media.sample_rate} Hz · {media.channels} canals"
        )
        mp3 = work / "prova_gravacio.mp3"
        started = time.perf_counter()
        convert_to_mp3(wav, mp3, MP3_KBPS, Mp3Tags(title="Prova de gravació"))
        took = time.perf_counter() - started
        info = probe(mp3)
        report.add(
            f"  MP3 {MP3_KBPS} kbps en {took:.1f} s: {mp3.stat().st_size / 1e6:.2f} MB · "
            f"{info.duration_s:.2f} s · {info.sample_rate} Hz · {info.channels} canals"
        )
        return media.has_audio and info.has_audio
    except Exception as error:
        report.add(f"  ERROR en comprovar o convertir: {explain(error)}")
        report.add(traceback.format_exc())
        return False


# --- report and entry point ---------------------------------------------------------------------------


def program_dir() -> Path:
    """The folder of ProvaGravacio.exe; the current folder when running from the source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def version_of(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "no instal·lat"


def describe_environment(report: Report) -> None:
    report.add(f"Data: {dt.datetime.now().isoformat(timespec='seconds')}")
    report.add(f"Sistema: {platform.platform()} ({platform.machine()})")
    report.add(
        f"Python: {sys.version.split()[0]} · empaquetat: {'sí' if getattr(sys, 'frozen', False) else 'no'}"
    )
    report.add(f"Executable: {sys.executable}")
    report.add(f"soundcard: {version_of('soundcard')} · cffi: {version_of('cffi')} · numpy: {np.__version__}")
    try:
        from passimaker.ffmpeg import locate

        paths = locate()
        report.add(f"FFmpeg: {paths.ffmpeg} · ffprobe: {paths.ffprobe}")
    except Exception as error:
        report.add(f"FFmpeg: no trobat ({error})")


def default_backend() -> Backend:
    return SoundcardBackend()


def write_report(report: Report, path: Path) -> Path:
    """Added at the end of the report next to the program (the user makes several runs and sends them all
    at once); in the temporary folder if that folder cannot be written."""
    text = report.text() + "\n" + "=" * 80 + "\n\n"
    for target in (path, Path(tempfile.gettempdir()) / path.name):
        try:
            with target.open("a", encoding="utf-8") as out:
                out.write(text)
            return target
        except OSError:
            continue
    raise OSError(f"No s'ha pogut escriure l'informe ({path})")


def ask(text: str) -> bool:
    """A Windows OK/Cancel box (no Qt in this tool); elsewhere, always yes."""
    if sys.platform != "win32":
        return True
    import ctypes

    return ctypes.windll.user32.MessageBoxW(None, text, "Prova de gravació", 0x40 | 0x1) == 1


def show_message(text: str) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, "Prova de gravació", 0x40)


def _ensure_streams() -> None:
    """Without a console, sys.stdout and sys.stderr are None (as in packaging/launcher.py)."""
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 (open until the end)
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prova de viabilitat de la gravació del so (bloc C08)")
    parser.add_argument("--durada", type=float, default=DEFAULT_DURATION_S, help="segons de gravació (20)")
    parser.add_argument(
        "--origen", type=int, help="número de l'origen de la llista (per defecte, la sortida)"
    )
    parser.add_argument("--llista", action="store_true", help="només llista els orígens")
    parser.add_argument("--sense-dispositiu", action="store_true", help="només les versions (la CI)")
    parser.add_argument("--conservar", action="store_true", help="no esborra el WAV ni l'MP3")
    parser.add_argument("--informe", help=f"fitxer de l'informe (per defecte, {REPORT_NAME} al costat)")
    parser.add_argument("--sense-avis", action="store_true", help="sense finestres de missatge")
    return parser.parse_args(argv)


def run(args: argparse.Namespace, report: Report, backend_factory: Callable[[], Backend]) -> bool:
    if args.sense_dispositiu:
        if sys.platform == "win32":
            importlib.import_module("soundcard")  # the package brings soundcard and its .h files
            report.add("soundcard s'importa correctament (sense obrir cap dispositiu)")
        return True
    backend = backend_factory()
    for line in backend.describe():
        report.add(line)
    report.add()
    report.add("=== Orígens ===")
    sources = backend.sources()
    for source in sources:
        report.add(f"  {source.label()}")
        report.add(f"      id: {source.id}")
    if args.llista:
        return True
    if not sources:
        report.add("No s'ha trobat cap origen per gravar.")
        return False
    if args.origen is not None and not 0 <= args.origen < len(sources):
        report.add(f"No hi ha l'origen {args.origen}: n'hi ha de 0 a {len(sources) - 1}.")
        return False
    source = sources[args.origen if args.origen is not None else 0]
    com_ok = com_check(report, backend, source)
    if not args.sense_avis and not ask(
        f"Es gravaran {args.durada:g} s de:\n{source.name}\n\nPosa en marxa la música i prem D'acord."
    ):
        report.add("Cancel·lat per l'usuari abans de gravar.")
        return False
    work = Path(tempfile.mkdtemp(prefix=WAV_PREFIX))
    started = time.perf_counter()
    try:
        ok = record(report, backend, source, args.durada, work)
    finally:
        report.add(f"  Temps total (gravació i conversió): {time.perf_counter() - started:.1f} s")
        if args.conservar:
            report.add(f"  Carpeta conservada: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    return ok and com_ok


def main(argv: list[str] | None = None, backend_factory: Callable[[], Backend] = default_backend) -> int:
    _ensure_streams()
    args = parse_args(argv)
    report = Report()
    report.add("Prova de gravació del so de PassiMaker (bloc C08)")
    describe_environment(report)
    report.add(f"Opcions: {' '.join(argv if argv is not None else sys.argv[1:]) or 'cap'}")
    try:
        ok = run(args, report, backend_factory)
    except Exception as error:
        report.add(f"ERROR: {explain(error)}")
        report.add(traceback.format_exc())
        ok = False
    report.add()
    report.add(f"Resultat final: {'CORRECTE' if ok else 'HA FALLAT'}")
    written = write_report(report, Path(args.informe) if args.informe else program_dir() / REPORT_NAME)
    print(report.text())
    if not args.sense_avis:
        show_message(f"Prova {'correcta' if ok else 'amb errors'}.\n\nInforme:\n{written}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
