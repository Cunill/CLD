"""Command-line tools (block B9): `passimaker-nou` and `passimaker-render`; `--autoprova` in B12.

passimaker-nou creates a project from a folder with the default values (the same steps as the
interface: import, automatic order, motions drawn by the controller); passimaker-render exports
it. Both write their messages in Catalan to stderr; Ctrl+C cancels an export cleanly.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

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
from passimaker.ffmpeg import probe
from passimaker.i18n import message
from passimaker.importer import FailedFile, ImportFailure, PhotoCandidate, import_paths, sort_candidates
from passimaker.model import OutputFormat, Photo, Project, ProjectController, Song
from passimaker.model.commands import AddPhotos, AddSongs, FitToMusic
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

_PROGRESS_STEP = 0.1
"""Without a terminal (CI, redirected output) progress is printed every 10 %."""


def build_new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="passimaker-nou",
        description=(
            "Crea un projecte .passimaker a partir d'una carpeta de fotos, amb els valors per defecte."
        ),
    )
    parser.add_argument("photos_dir", type=Path, help="Carpeta amb les fotos")
    parser.add_argument("music", type=Path, nargs="*", help="Fitxers de música, en ordre")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Fitxer .passimaker de sortida")
    parser.add_argument("--vertical", action="store_true", help="Format vertical 1080x1920")
    parser.add_argument("--ajustar", action="store_true", help="Ajusta les durades a la música")
    parser.add_argument("--llavor", type=int, default=None, help="Llavor dels moviments")
    return parser


def build_render_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="passimaker-render", description="Exporta un projecte .passimaker a MP4."
    )
    parser.add_argument("project", type=Path, help="Fitxer .passimaker")
    parser.add_argument("output", type=Path, help="Fitxer .mp4 de sortida")
    parser.add_argument("--sentinella", action="store_true", help="Mode de prova: magenta fora de la imatge")
    return parser


# --- passimaker-nou -------------------------------------------------------------------------------


def photo_from_candidate(candidate: PhotoCandidate, photo_id: str, output_format: OutputFormat) -> Photo:
    """A new photo with the default settings (its motion is drawn by the controller)."""
    return Photo(
        id=photo_id,
        path=candidate.path,
        relative_path=None,
        width=candidate.width,
        height=candidate.height,
        exif_orientation=candidate.exif_orientation,
        capture_time=candidate.capture_time,
        # §1.1: short side under half the video's (540 px in 1080p) -> "low resolution" icon.
        low_resolution=2 * min(candidate.width, candidate.height) < min(output_format.size),
    )


def song_from_file(path: Path, song_id: str) -> Song:
    """A new song with the default settings; raises FfmpegError if it cannot be read."""
    return Song(
        id=song_id, path=path.absolute(), relative_path=None, original_duration_s=probe(path).duration_s
    )


def new_project(
    photos_dir: Path,
    music: Sequence[Path] = (),
    *,
    name: str = "",
    output_format: OutputFormat = OutputFormat.HORIZONTAL,
    fit_to_music: bool = False,
    seed: int | None = None,
    err: TextIO | None = None,
) -> Project:
    """The project that passimaker-nou saves: every photo of the folder (not its subfolders), in the
    automatic order of §1.1, and the songs in the given order. Raises PassiMakerError."""
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
    base = Project(name=name, output_format=output_format, seed=0 if seed is None else seed)
    controller = ProjectController(base)
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
        f"{_clock(timeline.total_duration_s)})",
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
