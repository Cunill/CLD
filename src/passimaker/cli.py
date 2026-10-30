"""Command-line tools (block B9): `passimaker-nou` and `passimaker-render`; `--autoprova` (B12).

passimaker-nou creates a project from a folder with the default values (the same steps as the
interface: import, automatic order, motions drawn by the controller); passimaker-render exports
it. Both write their messages in Catalan to stderr; Ctrl+C cancels an export cleanly.
`PassiMaker.exe --autoprova` (packaging/launcher.py) runs `main_selftest`: it builds a project of
its own and exports 5 s of video without opening the window.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import secrets
import shutil
import sys
import tempfile
import threading
import time
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO, cast

import numpy as np
from PIL import Image

from passimaker import __version__
from passimaker.audio import song_from_file
from passimaker.common import CancelToken, PassiMakerError
from passimaker.export import (
    ERROR_DISK_FULL,
    ERROR_FAILED,
    ERROR_MISSING_FILES,
    ERROR_NO_PHOTOS,
    ERROR_WRITE,
    ExportResult,
    ExportStatus,
    export_project,
    missing_files,
)
from passimaker.ffmpeg import locate, probe
from passimaker.i18n import message
from passimaker.importer import FailedFile, ImportFailure, import_paths, photo_from_candidate, sort_candidates
from passimaker.model import BLACK_END_ID, BLACK_START_ID, OutputFormat, Project, ProjectController
from passimaker.model import new_project as empty_project
from passimaker.model.commands import AddPhotos, AddSongs, FitToMusic, SetPhotoDuration
from passimaker.projectio import EXTENSION, open_project, save_project
from passimaker.timeline import compute_timeline

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_IMPLEMENTED = 2

_FALLBACK_MESSAGES = {
    ERROR_NO_PHOTOS: "El projecte no té cap foto.",
    ERROR_MISSING_FILES: "No es troben alguns fitxers del projecte.",
    ERROR_DISK_FULL: "No hi ha prou espai al disc.",
    ERROR_WRITE: "No es pot escriure el vídeo en aquesta carpeta.",
    ERROR_FAILED: "L'exportació ha fallat per un error inesperat.",
    # Texts approved in decision 0007 (notes of B1 and B7).
    "ffmpeg.not_found": "No s'ha trobat FFmpeg. Torna a descomprimir el programa.",
    "ffmpeg.file_not_found": "No es troba el fitxer.",
    "ffmpeg.unreadable": "El fitxer està malmès o té un format que no es pot llegir.",
    "ffmpeg.no_audio": "El fitxer no té so.",
    "ffmpeg.encode_error": "No s'ha pogut crear el vídeo.",
    "ffmpeg.timeout": "FFmpeg no respon (el disc és molt lent?).",
    "ffmpeg.failed": "Error inesperat d'FFmpeg.",
    "projectio.corrupt": "El fitxer del projecte està malmès i no es pot obrir.",
    "projectio.newer_version": "Aquest projecte s'ha fet amb una versió més nova de PassiMaker.",
    "projectio.read_error": "No s'ha pogut llegir el fitxer del projecte.",
    "projectio.write_error": "No s'ha pogut desar el projecte.",
}
"""Catalan text of the errors until the catalogue arrives (B10, passimaker.i18n)."""

_IMPORT_FAILURES = {
    ImportFailure.UNSUPPORTED: "format no admès",
    ImportFailure.RAW: "fitxer RAW (no admès)",
    ImportFailure.CORRUPT: "fitxer malmès",
    ImportFailure.TOO_SMALL: "imatge massa petita",
    ImportFailure.NOT_FOUND: "no es troba",
}

NEW_SEED_LIMIT = 1_000_000
"""Without --llavor a new project gets a random seed below this (short enough to type it back).
Decision of the user (21/10/2026): each new project has different motions; the seed is saved in the
project, so the same project always gives the same video (rule 5)."""

_PROGRESS_STEP = 0.1
"""Without a terminal (CI, redirected output) progress is printed every 10 %."""


def build_new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="passimaker-nou",
        description="Crea un projecte .pmk a partir d'una carpeta de fotos, amb els valors per defecte.",
    )
    parser.add_argument("photos_dir", type=Path, help="Carpeta amb les fotos")
    parser.add_argument("music", type=Path, nargs="*", help="Fitxers de música, en ordre")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Fitxer .pmk de sortida")
    parser.add_argument("--vertical", action="store_true", help="Format vertical 1080x1920")
    parser.add_argument("--ajustar", action="store_true", help="Ajusta les durades a la música")
    parser.add_argument(
        "--llavor",
        type=int,
        default=None,
        help="Llavor dels moviments (sense aquesta opció, se'n tria una a l'atzar i es desa al projecte)",
    )
    return parser


def build_render_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="passimaker-render", description="Exporta un projecte .pmk a MP4.")
    parser.add_argument("project", type=Path, help="Fitxer .pmk")
    parser.add_argument("output", type=Path, help="Fitxer .mp4 de sortida")
    parser.add_argument("--sentinella", action="store_true", help="Mode de prova: magenta fora de la imatge")
    return parser


# --- passimaker-nou -------------------------------------------------------------------------------


def new_project(
    photos_dir: Path,
    music: Sequence[Path] = (),
    *,
    name: str = "",
    output_format: OutputFormat = OutputFormat.HORIZONTAL,
    fit_to_music: bool = False,
    seed: int | None = None,
    black_slide_s: float | None = None,
    err: TextIO | None = None,
) -> Project:
    """The project that passimaker-nou saves: the two black slides (M08), every photo of the folder (not
    its subfolders), in the automatic order of §1.1, and the songs in the given order. seed=None draws
    a random seed (saved in the project); black_slide_s=None keeps the default black slide duration.
    Raises PassiMakerError."""
    out = err if err is not None else sys.stderr
    result = import_paths([photos_dir.absolute()])
    for failure in result.failures:
        print(f"  S'omet {_failure_text(failure)}", file=out)
    if result.subfolder_photo_count:
        print(f"  No s'importen les {result.subfolder_photo_count} fotos de les subcarpetes.", file=out)
    candidates = sort_candidates(result.candidates)
    photos = tuple(
        photo_from_candidate(c, f"p{i:04d}", output_format) for i, c in enumerate(candidates, start=1)
    )
    songs = tuple(song_from_file(path, f"s{i:02d}") for i, path in enumerate(music, start=1))
    if seed is None:
        seed = secrets.randbelow(NEW_SEED_LIMIT)
    base = empty_project(name=name, output_format=output_format, seed=seed)
    controller = ProjectController(base)
    if black_slide_s is not None:
        controller.execute(SetPhotoDuration(frozenset({BLACK_START_ID, BLACK_END_ID}), black_slide_s))
    if photos:
        controller.execute(AddPhotos(photos))
    if songs:
        controller.execute(AddSongs(songs))
    if fit_to_music and songs and photos:
        controller.execute(FitToMusic())
    return controller.project


def _failure_text(failure: FailedFile) -> str:
    return f"{failure.path.name}: {_IMPORT_FAILURES.get(failure.reason, failure.reason.value)}"


def main_new(argv: list[str] | None = None) -> int:
    args = build_new_parser().parse_args(argv)
    _configure_logging()
    output: Path = args.output
    if output.suffix.lower() != EXTENSION:
        output = output.with_name(output.name + EXTENSION)
    if not args.photos_dir.is_dir():
        print(f"No es troba la carpeta {args.photos_dir}", file=sys.stderr)
        return EXIT_ERROR
    if args.ajustar and not args.music:
        print("--ajustar no fa res sense música.", file=sys.stderr)
    try:
        project = new_project(
            args.photos_dir,
            args.music,
            name=output.stem,
            output_format=OutputFormat.VERTICAL if args.vertical else OutputFormat.HORIZONTAL,
            fit_to_music=args.ajustar,
            seed=args.llavor,
        )
        if not project.photos:
            print(f"No hi ha cap foto per importar a {args.photos_dir}", file=sys.stderr)
            return EXIT_ERROR
        save_project(project, output)
    except PassiMakerError as error:
        print(_error_text(error.message_key, error.detail), file=sys.stderr)
        return EXIT_ERROR
    timeline = compute_timeline(project)
    print(
        f"Projecte desat: {output} ({len(project.photos)} fotos, {len(project.music.songs)} cançons, "
        f"{_clock(timeline.total_duration_s)}, llavor {project.seed})",
        file=sys.stderr,
    )
    return EXIT_OK


# --- passimaker-render ----------------------------------------------------------------------------


class _ProgressPrinter:
    """One updating line on a terminal; a line every 10 % otherwise."""

    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._interactive = out.isatty()
        self._next_step = 0.0

    def __call__(self, fraction: float, remaining_s: float | None) -> None:
        left = "" if remaining_s is None else f" (queden {_clock(remaining_s)})"
        if self._interactive:
            print(f"\rExportant… {fraction:4.0%}{left}   ", end="", file=self._out, flush=True)
        elif fraction >= self._next_step:
            print(f"Exportant… {fraction:.0%}{left}", file=self._out, flush=True)
            self._next_step = (int(fraction / _PROGRESS_STEP + 1e-9) + 1) * _PROGRESS_STEP

    def end(self) -> None:
        if self._interactive:
            print(file=self._out)


def render(project_path: Path, output: Path, *, sentinel: bool = False, err: TextIO | None = None) -> int:
    """Opens and exports a project; returns the exit code. Ctrl+C cancels."""
    out = err if err is not None else sys.stderr
    try:
        opened = open_project(project_path)
    except PassiMakerError as error:
        print(_error_text(error.message_key, error.detail), file=out)
        return EXIT_ERROR
    project = opened.project
    missing = missing_files(project)
    if missing:
        print(f"No es pot exportar: no es troben {len(missing)} fitxers:", file=out)
        for path in missing:
            print(f"  {path}", file=out)
        return EXIT_ERROR
    printer = _ProgressPrinter(out)
    cancel = CancelToken()
    results: list[ExportResult] = []
    started = time.monotonic()

    def work() -> None:
        results.append(export_project(project, output, progress=printer, cancel=cancel, sentinel=sentinel))

    worker = threading.Thread(target=work, name="passimaker-render")
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        cancel.cancel()
        worker.join()
    printer.end()
    elapsed = time.monotonic() - started
    result = results[0] if results else ExportResult(ExportStatus.ERROR, ERROR_FAILED, 0.0, 0)
    if result.status is ExportStatus.CANCELLED:
        print("Exportació cancel·lada: no s'ha desat cap fitxer.", file=out)
        return EXIT_ERROR
    if result.status is ExportStatus.ERROR:
        print(_error_text(result.reason_key or ERROR_FAILED, ""), file=out)
        return EXIT_ERROR
    frames = round(result.duration_s * compute_timeline(project).fps)
    print(
        f"Vídeo desat: {output} ({_clock(result.duration_s)}, {_megabytes(result.size_bytes)}). "
        f"{frames} imatges en {elapsed:.1f} s ({frames / elapsed if elapsed > 0 else 0:.1f} imatges/s).",
        file=out,
    )
    return EXIT_OK


def main_render(argv: list[str] | None = None) -> int:
    args = build_render_parser().parse_args(argv)
    _configure_logging()
    return render(args.project, args.output, sentinel=args.sentinella)


# --- --autoprova -----------------------------------------------------------------------------------

SELF_TEST_PHOTOS = ((1600, 1200), (1200, 1600), (1920, 1080), (1500, 1500))
"""Landscape, portrait and square, so every fit of the compositor runs."""
SELF_TEST_DURATION_S = 5.0
"""The length the plan asks for (B12): the photos are fitted to a song of exactly 5 s."""
SELF_TEST_TOLERANCE_S = 0.1
SELF_TEST_BLACK_SLIDE_S = 0.5
"""The black slides of the self-test (M08) are short, so the 5 s still leave about 1 s per photo."""
SELF_TEST_SEED = 12
"""Fixed: the self-test always makes the same video (rule 5)."""
SELF_TEST_TONE_HZ = 440.0
_SELF_TEST_SAMPLE_RATE = 48_000
_SELF_TEST_NAME = "autoprova"


def build_selftest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="PassiMaker.exe --autoprova",
        description="Comprova que el programa funciona: exporta un vídeo de 5 s sense obrir la finestra.",
    )
    parser.add_argument(
        "--conservar",
        type=Path,
        default=None,
        help="Carpeta on es deixen les fotos, la música, el projecte i el vídeo de la prova",
    )
    parser.add_argument("--informe", type=Path, default=None, help="Fitxer on s'escriu també l'informe")
    return parser


def write_selftest_files(folder: Path) -> tuple[Path, Path]:
    """The photos (gradients, JPEG) and the song (a 440 Hz tone, WAV) of the self-test, generated here:
    the packaged program carries no test data. Returns (photo folder, song)."""
    photos = folder / "fotos"
    photos.mkdir(parents=True, exist_ok=True)
    for index, (width, height) in enumerate(SELF_TEST_PHOTOS, start=1):
        x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
        y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
        hue = index / len(SELF_TEST_PHOTOS)
        rgb = np.stack(
            np.broadcast_arrays(40 + 180 * x, 40 + 180 * y, np.full_like(x, 60 + 150 * hue)), axis=-1
        )
        Image.fromarray(rgb.astype(np.uint8)).save(photos / f"foto_{index}.jpg", quality=90)
    song = folder / "to_440.wav"
    frames = round(SELF_TEST_DURATION_S * _SELF_TEST_SAMPLE_RATE)
    t = np.arange(frames, dtype=np.float64) / _SELF_TEST_SAMPLE_RATE
    tone = (0.3 * 32767 * np.sin(2 * np.pi * SELF_TEST_TONE_HZ * t)).astype("<i2")
    with wave.open(str(song), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(_SELF_TEST_SAMPLE_RATE)
        out.writeframes(np.repeat(tone[:, None], 2, axis=1).tobytes())
    return photos, song


def self_test(work_dir: Path, *, err: TextIO | None = None) -> int:
    """Creates a project in work_dir (photos, song, .pmk), exports it and checks the video with
    ffprobe. Returns the exit code; every step is reported in Catalan."""
    out = err if err is not None else sys.stderr
    print(f"Autoprova de PassiMaker {__version__}", file=out)
    try:
        paths = locate()
        print(f"  FFmpeg: {paths.ffmpeg}", file=out)
    except PassiMakerError as error:
        print(_error_text(error.message_key, error.detail), file=out)
        return EXIT_ERROR
    portaudio = portaudio_version()
    if portaudio is None:
        print(
            "Autoprova incorrecta: no es pot carregar PortAudio (la previsualització aniria sense so).",
            file=out,
        )
        return EXIT_ERROR
    print(f"  So: {portaudio}", file=out)
    try:
        photos, song = write_selftest_files(work_dir)
        project = new_project(
            photos,
            [song],
            name=_SELF_TEST_NAME,
            fit_to_music=True,
            seed=SELF_TEST_SEED,
            black_slide_s=SELF_TEST_BLACK_SLIDE_S,
            err=out,
        )
        project_path = work_dir / f"{_SELF_TEST_NAME}{EXTENSION}"
        save_project(project, project_path)
        print(f"  Projecte: {project_path} ({len(project.photos)} fotos, 1 cançó)", file=out)
    except PassiMakerError as error:
        print(_error_text(error.message_key, error.detail), file=out)
        return EXIT_ERROR
    video = work_dir / f"{_SELF_TEST_NAME}.mp4"
    if render(project_path, video, err=out) != EXIT_OK:
        return EXIT_ERROR
    try:
        info = probe(video)
    except PassiMakerError as error:
        print(_error_text(error.message_key, error.detail), file=out)
        return EXIT_ERROR
    problems: list[str] = []
    if (info.width, info.height) != OutputFormat.HORIZONTAL.size or not info.has_video:
        problems.append(f"la imatge és de {info.width}×{info.height}")
    if not info.has_audio:
        problems.append("no té so")
    if abs(info.duration_s - SELF_TEST_DURATION_S) > SELF_TEST_TOLERANCE_S:
        problems.append(f"dura {info.duration_s:.2f} s en lloc de {SELF_TEST_DURATION_S:.0f} s")
    if problems:
        print(f"Autoprova incorrecta: el vídeo {', '.join(problems)}.", file=out)
        return EXIT_ERROR
    print(
        f"Autoprova correcta: {info.width}×{info.height}, {info.duration_s:.2f} s, amb so.",
        file=out,
    )
    return EXIT_OK


def portaudio_version() -> str | None:
    """The PortAudio library the preview plays through (B13), or None if it cannot be loaded. Only loads
    it: the self-test does not need a sound device (the CI has none)."""
    try:
        sounddevice: Any = importlib.import_module("sounddevice")
        return str(sounddevice.get_portaudio_version()[1])
    except (ImportError, OSError):
        return None


class _Tee:
    """Writes to stderr (if the program has one: a windowed PassiMaker.exe may not) and to the report."""

    def __init__(self, *streams: TextIO | None) -> None:
        self._streams = [s for s in streams if s is not None]

    def write(self, text: str) -> int:
        for stream in self._streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def isatty(self) -> bool:
        return False


def main_selftest(argv: list[str] | None = None) -> int:
    """`PassiMaker.exe --autoprova [--conservar CARPETA] [--informe FITXER]`: 0 if everything works.
    Without --conservar the files go to a temporary folder that is deleted at the end."""
    args = build_selftest_parser().parse_args(argv)
    report = None
    if args.informe is not None:
        args.informe.parent.mkdir(parents=True, exist_ok=True)
        report = args.informe.open("w", encoding="utf-8")
    try:
        out = cast(TextIO, _Tee(sys.stderr, report))
        logging.basicConfig(level=logging.WARNING, format="Avís: %(message)s", stream=out)
        if args.conservar is not None:
            args.conservar.mkdir(parents=True, exist_ok=True)
            return self_test(args.conservar.absolute(), err=out)
        work_dir = Path(tempfile.mkdtemp(prefix="passimaker-autoprova-"))
        try:
            return self_test(work_dir, err=out)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
    finally:
        if report is not None:
            report.close()


# --- Text -----------------------------------------------------------------------------------------


def _configure_logging() -> None:
    """Warnings of the core (unreadable song or photo...) go to stderr."""
    logging.basicConfig(level=logging.WARNING, format="Avís: %(message)s")


def _error_text(key: str, detail: str) -> str:
    text = message(key)
    if text == key:
        text = _FALLBACK_MESSAGES.get(key, key)
    return f"Error: {text}" + (f" ({detail})" if detail else "")


def _clock(seconds: float) -> str:
    """4:30 (minutes:seconds), as in "Vídeo desat (4:30, 245 MB)" (§1.9)."""
    total = max(0, round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def _megabytes(size: int) -> str:
    return f"{size / 1_000_000:.0f} MB" if size >= 10_000_000 else f"{size / 1_000_000:.1f} MB"
