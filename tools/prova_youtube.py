"""C02 spike: does yt-dlp work from a PyInstaller ZIP on Windows? (docs/sessions/C02.md)

ProvaYoutube.exe (packaging/ProvaYoutube.spec, no console) runs this script twice, with Deno and without
any JavaScript runtime. Each run searches 3 results for a fixed query, downloads the best audio of a fixed
Creative Commons video to a temporary folder (no yt-dlp postprocessing) and checks it with
passimaker.ffmpeg.probe. Everything goes to a text report next to the executable: versions, proxy, times,
sizes, every yt-dlp message and full tracebacks. A message box says where the report is.

Not part of the program: passimaker.youtube (block C03) is the real implementation. Importing this module
does not import yt_dlp nor open any connection; the network is used only inside run_variant().

  ProvaYoutube.exe [--informe FITXER] [--sense-xarxa] [--conservar] [--sense-avis]
  uv run python tools/prova_youtube.py [same options]
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import traceback
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

LINK = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
"""Big Buck Bunny (Blender Foundation, Creative Commons Attribution), on the Blender channel since 2014."""
QUERY = "Big Buck Bunny Blender"
SEARCH_COUNT = 3
REPORT_NAME = "informe_prova_youtube.txt"
SOCKET_TIMEOUT_S = 30
PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY")
DENO_EXE = "deno.exe" if sys.platform == "win32" else "deno"

YdlFactory = Callable[[dict[str, Any]], Any]
"""Builds a yt_dlp.YoutubeDL from its options (the tests pass a fake)."""


@dataclass
class Variant:
    label: str
    js_runtimes: dict[str, dict[str, str]]


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)

    def add(self, text: str = "") -> None:
        self.lines.extend(text.splitlines() or [""])

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


class YdlLogger:
    """Receives every yt-dlp message, so the report has them all, warnings and debug included."""

    def __init__(self, report: Report) -> None:
        self.report = report
        self.warnings: list[str] = []
        self.deno_runs = 0

    def debug(self, msg: str) -> None:
        if "Running deno" in msg:
            self.deno_runs += 1
        self.report.add(f"    [yt-dlp] {msg}")

    def info(self, msg: str) -> None:
        self.report.add(f"    [yt-dlp] {msg}")

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)
        self.report.add(f"    [yt-dlp AVÍS] {msg}")

    def error(self, msg: str) -> None:
        self.report.add(f"    [yt-dlp ERROR] {msg}")


def mask_proxy(url: str) -> str:
    """Hides the password of a proxy URL (user:password@host)."""
    return re.sub(r"(//[^:/@]+):[^@/]*@", r"\1:***@", url)


def program_dir() -> Path:
    """The folder of ProvaYoutube.exe; the current folder when running from the source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def report_path(requested: str | None) -> Path:
    if requested:
        return Path(requested)
    return program_dir() / REPORT_NAME


def find_deno() -> Path | None:
    """deno.exe of the package (bin/, next to ffmpeg.exe) or of the `deno` Python package."""
    bundle = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle, str):
        candidate = Path(bundle) / DENO_EXE
        return candidate if candidate.is_file() else None
    try:
        from deno import find_deno_bin  # pyright: ignore[reportMissingTypeStubs]
    except ImportError:
        return None
    try:
        return Path(find_deno_bin())
    except FileNotFoundError:
        return None


def library_versions() -> str:
    """From the modules, not the package metadata: PyInstaller does not bring the metadata."""
    try:
        import yt_dlp.version

        yt_dlp_version: str = yt_dlp.version.__version__
    except ImportError:
        yt_dlp_version = "no instal·lat"
    try:
        from yt_dlp_ejs import version as ejs_version  # pyright: ignore[reportMissingTypeStubs]
    except ImportError:
        ejs_version = "no instal·lat"
    return f"yt-dlp: {yt_dlp_version} · yt-dlp-ejs: {ejs_version}"


def describe_environment(report: Report, deno: Path | None) -> None:
    report.add(f"Data: {dt.datetime.now().isoformat(timespec='seconds')}")
    report.add(f"Sistema: {platform.platform()} ({platform.machine()})")
    report.add(
        f"Python: {sys.version.split()[0]} · empaquetat: {'sí' if getattr(sys, 'frozen', False) else 'no'}"
    )
    report.add(f"Executable: {sys.executable}")
    report.add(library_versions())
    if deno is None:
        report.add("Deno: no trobat")
    else:
        report.add(f"Deno: {deno} ({deno.stat().st_size / 1e6:.1f} MB) · versió: {deno_version(deno)}")
    report.add(f"Scripts de yt-dlp-ejs: {ejs_scripts()}")
    try:
        from passimaker.ffmpeg import locate

        paths = locate()
        report.add(f"FFmpeg: {paths.ffmpeg} · ffprobe: {paths.ffprobe}")
    except Exception as error:
        report.add(f"FFmpeg: no trobat ({error})")
    for name in PROXY_VARS:
        if os.environ.get(name):
            report.add(f"Variable {name} = {mask_proxy(os.environ[name])}")
    proxies = urllib.request.getproxies()  # environment and, on Windows, the system settings (registry)
    shown = {k: mask_proxy(v) for k, v in sorted(proxies.items()) if k in {"http", "https", "all"}}
    report.add(f"Servidor intermediari que veu Python: {shown or 'cap'}")


def deno_version(deno: Path) -> str:
    """Asks yt-dlp, as it will when solving the challenges (it runs `deno --version` itself)."""
    try:
        from yt_dlp.utils._jsruntime import DenoJsRuntime  # pyright: ignore[reportMissingTypeStubs]

        info = DenoJsRuntime(str(deno)).info
        return info.version if info is not None else "yt-dlp no el pot executar"
    except Exception as error:
        return f"error: {error!r}"


def ejs_scripts() -> str:
    """The JavaScript that Deno runs to solve YouTube's challenges, as yt-dlp finds it."""
    try:
        from yt_dlp.dependencies import yt_dlp_ejs  # pyright: ignore[reportMissingTypeStubs]

        if yt_dlp_ejs is None:
            return "yt-dlp no els troba"
        import yt_dlp_ejs.yt.solver as solver  # pyright: ignore[reportMissingTypeStubs]

        return f"core {len(solver.core())} caràcters, lib {len(solver.lib())} caràcters"
    except Exception as error:
        return f"error: {error!r}"


def default_ydl_factory(options: dict[str, Any]) -> Any:
    import yt_dlp

    return yt_dlp.YoutubeDL(cast(Any, options))


@contextlib.contextmanager
def step(report: Report, name: str, results: dict[str, bool]) -> Iterator[None]:
    report.add(f"  -- {name}")
    start = time.perf_counter()
    try:
        yield
    except Exception:
        report.add(f"  -- {name}: ERROR en {time.perf_counter() - start:.1f} s")
        report.add(traceback.format_exc())
        results[name] = False
    else:
        report.add(f"  -- {name}: correcte en {time.perf_counter() - start:.1f} s")
        results[name] = True


def run_variant(
    report: Report, variant: Variant, work: Path, ydl_factory: YdlFactory = default_ydl_factory
) -> dict[str, bool]:
    """Search, download and check one audio. Returns each step's result."""
    report.add()
    report.add(f"=== {variant.label} ===")
    logger = YdlLogger(report)
    folder = work / re.sub(r"\W+", "_", variant.label)
    folder.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {
        "logger": logger,
        "verbose": True,
        "noprogress": True,
        "socket_timeout": SOCKET_TIMEOUT_S,
        "retries": 1,
        "extractor_retries": 1,
        "js_runtimes": variant.js_runtimes,
        "cachedir": False,  # nothing written outside the temporary folder
        "noplaylist": True,
        "format": "bestaudio/best",
        "fixup": "never",  # no FFmpeg from yt-dlp: the conversion is passimaker.ffmpeg's job
        "postprocessors": [],
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
    }
    results: dict[str, bool] = {}
    downloaded: list[Path] = []

    with step(report, f"Cerca de {SEARCH_COUNT} resultats: {QUERY!r}", results):
        with ydl_factory({**options, "extract_flat": "in_playlist"}) as ydl:
            found = ydl.extract_info(f"ytsearch{SEARCH_COUNT}:{QUERY}", download=False)
        entries = list(found.get("entries") or [])
        for entry in entries:
            report.add(
                f"     · {entry.get('id')} · {entry.get('title')!r} · {entry.get('channel')!r} · "
                f"{entry.get('duration')} s"
            )
        if len(entries) != SEARCH_COUNT:
            raise RuntimeError(f"{len(entries)} resultats en comptes de {SEARCH_COUNT}")

    with step(report, f"Baixada del millor àudio: {LINK}", results):
        with ydl_factory(options) as ydl:
            info = ydl.extract_info(LINK, download=True)
        report.add(
            f"     · {info.get('title')!r} · llicència: {info.get('license')!r}"
            f" · format {info.get('format_id')} ({info.get('ext')}, {info.get('acodec')},"
            f" {info.get('abr')} kbps)"
        )
        for item in info.get("requested_downloads") or []:
            downloaded.append(Path(item["filepath"]))
        if not downloaded:
            raise RuntimeError("yt-dlp no diu quin fitxer ha baixat")
        for path in downloaded:
            report.add(f"     · fitxer: {path.name} · {path.stat().st_size / 1e6:.2f} MB")

    if downloaded:
        with step(report, "Comprovació amb passimaker.ffmpeg.probe", results):
            from passimaker.ffmpeg import probe

            media = probe(downloaded[0])
            report.add(
                f"     · {media.duration_s:.1f} s · àudio: {media.has_audio} · {media.sample_rate} Hz · "
                f"{media.channels} canals · vídeo: {media.has_video}"
            )
            if not media.has_audio:
                raise RuntimeError("el fitxer baixat no té àudio")

    report.add(f"  Deno executat {logger.deno_runs} vegades · avisos de yt-dlp: {len(logger.warnings)}")
    return results


def summary(report: Report, all_results: dict[str, dict[str, bool]]) -> bool:
    report.add()
    report.add("=== Resum ===")
    for label, results in all_results.items():
        ok = bool(results) and all(results.values())
        report.add(f"{label}: {'CORRECTE' if ok else 'HA FALLAT'}")
        for name, passed in results.items():
            report.add(f"  {'sí' if passed else 'NO'} · {name}")
    first = next(iter(all_results.values()), {})
    return bool(first) and all(first.values())


def write_report(report: Report, path: Path) -> Path:
    """Next to the program; in the temporary folder if that folder cannot be written."""
    try:
        path.write_text(report.text(), encoding="utf-8")
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / path.name
        fallback.write_text(report.text(), encoding="utf-8")
        return fallback


def show_message(text: str) -> None:
    """A Windows message box (no Qt in this tool), so the user knows the test has finished."""
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, "Prova de YouTube", 0x40)


def _ensure_streams() -> None:
    """Without a console, sys.stdout and sys.stderr are None (as in packaging/launcher.py)."""
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 (open until the end)
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prova de viabilitat de yt-dlp (bloc C02)")
    parser.add_argument(
        "--informe", help=f"fitxer de l'informe (per defecte, {REPORT_NAME} al costat del programa)"
    )
    parser.add_argument("--sense-xarxa", action="store_true", help="només les versions; cap connexió (la CI)")
    parser.add_argument("--conservar", action="store_true", help="no esborra la carpeta temporal")
    parser.add_argument("--sense-avis", action="store_true", help="no mostra el missatge final")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, ydl_factory: YdlFactory = default_ydl_factory) -> int:
    _ensure_streams()
    args = parse_args(argv)
    report = Report()
    report.add("Prova de YouTube de PassiMaker (bloc C02)")
    deno = find_deno()
    describe_environment(report, deno)
    ok = deno is not None
    if not args.sense_xarxa:
        work = Path(tempfile.mkdtemp(prefix="prova_youtube_"))
        report.add(f"Carpeta temporal: {work}")
        variants = [Variant("Amb Deno", {"deno": {"path": str(deno)}} if deno else {"deno": {}})]
        variants.append(Variant("Sense entorn JavaScript", {}))
        all_results = {v.label: run_variant(report, v, work, ydl_factory) for v in variants}
        ok = summary(report, all_results) and ok
        if deno is not None:
            report.add(
                "Deno encara hi és en acabar (Windows Defender no l'ha tret): "
                + ("sí" if deno.is_file() else "NO")
            )
        if args.conservar:
            report.add(f"Carpeta temporal conservada: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    report.add()
    report.add(f"Resultat final: {'CORRECTE' if ok else 'HA FALLAT'}")
    written = write_report(report, report_path(args.informe))
    print(report.text())
    if not args.sense_avis:
        show_message(f"Prova {'correcta' if ok else 'amb errors'}.\n\nInforme:\n{written}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
