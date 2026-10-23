"""Draws packaging/PassiMaker.ico (block B12): a photo with mountains and a sun on a rounded tile.

The icon is generated, not drawn by hand, so it can be changed here and regenerated:
`uv run python packaging/generar_icona.py`. The output is always the same (no randomness).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ICON = Path(__file__).resolve().parent / "PassiMaker.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
_CANVAS = 1024
"""Drawn 4× larger than the biggest size and reduced, so the edges are smooth."""

_TILE = (32, 64, 112)
_FRAME = (250, 248, 240)
_SKY = (120, 180, 230)
_SUN = (255, 200, 60)
_FAR = (70, 130, 90)
_NEAR = (40, 95, 65)


def draw(size: int = _CANVAS) -> Image.Image:
    s = size / _CANVAS
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((0, 0, size - 1, size - 1), radius=round(180 * s), fill=_TILE)
    # A second photo behind, tilted by its corners: a slideshow, not a single picture.
    pen.polygon(
        [(250 * s, 170 * s), (900 * s, 260 * s), (840 * s, 700 * s), (190 * s, 610 * s)], fill=(90, 120, 170)
    )
    pen.rectangle((120 * s, 270 * s, 800 * s, 820 * s), fill=_FRAME)
    left, top, right, bottom = 165 * s, 315 * s, 755 * s, 690 * s
    pen.rectangle((left, top, right, bottom), fill=_SKY)
    pen.ellipse((560 * s, 360 * s, 680 * s, 480 * s), fill=_SUN)
    pen.polygon([(left, bottom), (340 * s, 450 * s), (500 * s, bottom)], fill=_FAR)
    pen.polygon([(330 * s, bottom), (560 * s, 500 * s), (right, 620 * s), (right, bottom)], fill=_NEAR)
    return image


def main() -> None:
    large = draw()
    images = [large.resize((n, n), Image.Resampling.LANCZOS) for n in SIZES]
    images[-1].save(ICON, format="ICO", sizes=[(n, n) for n in SIZES], append_images=images[:-1])
    print(f"Icona desada: {ICON}")


if __name__ == "__main__":
    main()
