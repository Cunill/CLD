"""Builds the program icons from packaging/icona.png: two film-strip photos on a rounded navy tile.

icona.png (512 px, transparent corners) is the source drawing; it is an image, not code. From it:
- packaging/PassiMaker.ico, 16–256 px: the icon of PassiMaker.exe (packaging/PassiMaker.spec);
- src/passimaker/ui/app_icon.png, 256 px: the icon of the window (passimaker.ui.app).

To change the icon: replace icona.png and run `uv run python packaging/generar_icona.py`.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "packaging" / "icona.png"
ICON = ROOT / "packaging" / "PassiMaker.ico"
WINDOW_ICON = ROOT / "src" / "passimaker" / "ui" / "app_icon.png"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    images = [source.resize((n, n), Image.Resampling.LANCZOS) for n in SIZES]
    images[-1].save(ICON, format="ICO", sizes=[(n, n) for n in SIZES], append_images=images[:-1])
    images[-1].save(WINDOW_ICON, optimize=True)
    print(f"Icones desades: {ICON} i {WINDOW_ICON}")


if __name__ == "__main__":
    main()
