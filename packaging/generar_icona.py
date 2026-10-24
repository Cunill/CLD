"""Builds the program icons: two photos on a rounded navy tile that is a strip of film.

packaging/icona.png (512 px, transparent corners) is the drawing of the photos and the tile; it is an image,
not code. This script adds the film perforations on the tile, in two rows above and below the photos, and
writes:
- packaging/PassiMaker.ico, 16–256 px: the icon of PassiMaker.exe (packaging/PassiMaker.spec);
- src/passimaker/ui/app_icon.png, 256 px: the icon of the window (passimaker.ui.app).

To change the icon: edit icona.png or the perforations below and run
`uv run python packaging/generar_icona.py`. The output is always the same (no randomness).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "packaging" / "icona.png"
ICON = ROOT / "packaging" / "PassiMaker.ico"
WINDOW_ICON = ROOT / "src" / "passimaker" / "ui" / "app_icon.png"
SIZES = (16, 24, 32, 48, 64, 128, 256)

_SCALE = 4
"""The perforations are drawn 4× larger than icona.png and reduced, so their edges are smooth."""
_HOLE = (250, 248, 240, 255)
_HOLES = 9
_HOLE_WIDTH, _HOLE_HEIGHT, _HOLE_RADIUS = 22, 30, 5
_FIRST_X, _LAST_X = 40, 472
"""Inside the rounded corners of the tile (radius about 92 px)."""
_ROWS_Y = (28, 454)
"""Top of each row: the photos take y 81–427 of icona.png."""


def draw() -> Image.Image:
    source = Image.open(SOURCE).convert("RGBA")
    big = (source.width * _SCALE, source.height * _SCALE)
    holes = Image.new("RGBA", big, (0, 0, 0, 0))
    pen = ImageDraw.Draw(holes)
    pitch = (_LAST_X - _FIRST_X - _HOLE_WIDTH) / (_HOLES - 1)
    for top in _ROWS_Y:
        for i in range(_HOLES):
            left = _FIRST_X + i * pitch
            box = (left, top, left + _HOLE_WIDTH, top + _HOLE_HEIGHT)
            pen.rounded_rectangle([v * _SCALE for v in box], radius=_HOLE_RADIUS * _SCALE, fill=_HOLE)
    source.alpha_composite(holes.resize(source.size, Image.Resampling.LANCZOS))
    return source


def main() -> None:
    large = draw()
    images = [large.resize((n, n), Image.Resampling.LANCZOS) for n in SIZES]
    images[-1].save(ICON, format="ICO", sizes=[(n, n) for n in SIZES], append_images=images[:-1])
    images[-1].save(WINDOW_ICON, optimize=True)
    print(f"Icones desades: {ICON} i {WINDOW_ICON}")


if __name__ == "__main__":
    main()
