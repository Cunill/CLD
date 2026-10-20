"""Command-line tools (block B9): `passimaker-nou` and `passimaker-render`; `--autoprova` in B12."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_IMPLEMENTED = 2


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


def main_new(argv: list[str] | None = None) -> int:
    build_new_parser().parse_args(argv)
    print("passimaker-nou: encara no implementat (bloc B9)", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


def main_render(argv: list[str] | None = None) -> int:
    build_render_parser().parse_args(argv)
    print("passimaker-render: encara no implementat (bloc B9)", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED
