"""Full de contactes dels moviments (fita F1) i, opcionalment, un vídeo de mostra.

Per a cada foto d'una carpeta dibuixa el llenç (la foto, o la foto sobre el fons difuminat) amb
la finestra inicial en verd i la final en vermell, numerades en l'ordre del passi. Amb --video
genera també un MP4 senzill (fosa encadenada i moviment) per veure la velocitat real.

Ús:
    uv run python tools/full_contactes_moviments.py <carpeta> -o full.png [--video mostra.mp4]
        [--vertical] [--intensitat suau|mitjana|marcada] [--llavor N] [--durada 5]

És una eina de revisió: el compositor real del programa és el bloc B6.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont, ImageOps

from passimaker.model.types import (
    FitMode,
    Intensity,
    MotionMode,
    MotionType,
    OutputFormat,
    PhotoMotion,
    ResolvedFit,
)
from passimaker.motion import (
    INTENSITY_PRESETS,
    FitDecision,
    MotionAmounts,
    MotionRequest,
    draw_motions,
    resolve_fit,
    window_at,
    window_rect,
)

EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".webp"}
WORK_SIZE = 1600
CELL_WIDTH = 440
COLUMNS = 4
CROSSFADE_S = 1.0
FADE_IN_S, FADE_OUT_S = 1.0, 2.0
FPS = 30

LABELS = {
    MotionType.ZOOM_IN: "Apropar",
    MotionType.ZOOM_OUT: "Allunyar",
    MotionType.PAN_LEFT: "Desplaçar a l'esquerra",
    MotionType.PAN_RIGHT: "Desplaçar a la dreta",
    MotionType.PAN_UP: "Desplaçar amunt",
    MotionType.PAN_DOWN: "Desplaçar avall",
    MotionType.COMBINED: "Combinat",
    MotionType.NONE: "Cap",
}
INTENSITIES = {"suau": Intensity.SOFT, "mitjana": Intensity.MEDIUM, "marcada": Intensity.STRONG}


@dataclass
class Item:
    path: Path
    width: int
    height: int
    """Original size after EXIF orientation."""
    image: NDArray[np.uint8]
    """Working copy (long side <= WORK_SIZE)."""
    fit: FitDecision
    motion: PhotoMotion | None = None
    canvas: NDArray[np.uint8] | None = None


def load_items(folder: Path, output_format: OutputFormat) -> list[Item]:
    pillow_heif.register_heif_opener()
    items: list[Item] = []
    for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS):
        try:
            with Image.open(path) as raw:
                img = ImageOps.exif_transpose(raw)
                if img.mode.startswith("I"):  # 16-bit greyscale: scale to 8 bits
                    img = Image.fromarray((np.asarray(img, dtype=np.float64) / 257).astype(np.uint8))
                img = img.convert("RGB")
        except OSError:
            print(f"S'omet {path.name}: no es pot llegir", file=sys.stderr)
            continue
        width, height = img.size
        img.thumbnail((WORK_SIZE, WORK_SIZE))
        fit = resolve_fit(width, height, output_format, FitMode.AUTO)
        items.append(Item(path, width, height, np.asarray(img, dtype=np.uint8), fit))
    return items


def visible_duration(index: int, count: int, duration: float) -> float:
    half = min(CROSSFADE_S, duration / 2) / 2
    return duration + half * ((index > 0) + (index < count - 1))


def assign_motions(
    items: list[Item], output_format: OutputFormat, amounts: MotionAmounts, seed: int, duration: float
) -> None:
    requests = [
        MotionRequest(
            photo_id=f"{i:04d}",
            width=item.width,
            height=item.height,
            visible_duration_s=visible_duration(i, len(items), duration),
            fit=item.fit,
            output_format=output_format,
            mode=MotionMode.AUTO,
            manual_type=None,
            draw_count=0,
        )
        for i, item in enumerate(items)
    ]
    motions = draw_motions(requests, seed, amounts)
    for request, item in zip(requests, items, strict=True):
        item.motion = motions[request.photo_id]


def build_canvas(item: Item) -> NDArray[np.uint8]:
    """Working-resolution canvas: the photo (FILL) or the photo centred on a blurred/black background."""
    img = item.image
    if item.fit.fit is ResolvedFit.FILL:
        return img
    h, w = img.shape[:2]
    scale = w / item.width
    cw, ch = round(item.fit.canvas_width * scale), round(item.fit.canvas_height * scale)
    if item.fit.fit is ResolvedFit.BLACK:
        canvas = np.zeros((ch, cw, 3), dtype=np.uint8)
    else:
        cover = max(cw / w, ch / h)
        big = cv2.resize(
            img, (max(cw, round(w * cover)), max(ch, round(h * cover))), interpolation=cv2.INTER_AREA
        )
        y0, x0 = (big.shape[0] - ch) // 2, (big.shape[1] - cw) // 2
        small = cv2.resize(
            big[y0 : y0 + ch, x0 : x0 + cw], (max(1, cw // 8), max(1, ch // 8)), interpolation=cv2.INTER_AREA
        )
        blurred = cv2.GaussianBlur(small, (0, 0), sigmaX=max(1.0, small.shape[1] / 40))
        canvas = (cv2.resize(blurred, (cw, ch), interpolation=cv2.INTER_LINEAR) * 0.7).astype(np.uint8)
    y, x = (ch - h) // 2, (cw - w) // 2
    canvas[y : y + h, x : x + w] = img
    return canvas


FONT_CANDIDATES = ("DejaVuSans.ttf", "segoeui.ttf", "arial.ttf")


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A font with Catalan characters (the bundled default lacks "ç")."""
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def contact_sheet(items: list[Item], output_format: OutputFormat, title: str) -> Image.Image:
    font = load_font(14)
    title_font = load_font(19)
    cells: list[Image.Image] = []
    for index, item in enumerate(items):
        assert item.motion is not None and item.canvas is not None
        canvas = Image.fromarray(item.canvas)
        scale = CELL_WIDTH / canvas.width
        if canvas.height * scale > CELL_WIDTH:
            scale = CELL_WIDTH / canvas.height
        shown = canvas.resize((max(1, round(canvas.width * scale)), max(1, round(canvas.height * scale))))
        cell = Image.new("RGB", (CELL_WIDTH, CELL_WIDTH + 44), (245, 245, 240))
        ox, oy = (CELL_WIDTH - shown.width) // 2, (CELL_WIDTH - shown.height) // 2
        cell.paste(shown, (ox, oy))
        draw = ImageDraw.Draw(cell)
        px = shown.width / item.fit.canvas_width
        centres = []
        for window, colour in ((item.motion.start, (0, 200, 60)), (item.motion.end, (230, 30, 30))):
            left, top, right, bottom = window_rect(window, item.fit, output_format)
            box = (ox + left * px, oy + top * px, ox + right * px, oy + bottom * px)
            draw.rectangle(box, outline=colour, width=3)
            centres.append(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
        draw.line([centres[0], centres[1]], fill=(255, 210, 0), width=3)
        draw.ellipse(
            (centres[1][0] - 5, centres[1][1] - 5, centres[1][0] + 5, centres[1][1] + 5), fill=(255, 210, 0)
        )
        zoom = item.motion.end.scale / item.motion.start.scale - 1
        label = f"{index + 1}. {LABELS[item.motion.type]}  ·  zoom {zoom * 100:+.0f} %"
        fit = {
            ResolvedFit.FILL: "omplir",
            ResolvedFit.BLUR: "fons difuminat",
            ResolvedFit.BLACK: "fons negre",
        }
        draw.text((8, CELL_WIDTH + 2), label, fill=(20, 20, 20), font=font)
        draw.text(
            (8, CELL_WIDTH + 22), f"{item.path.name} · {fit[item.fit.fit]}", fill=(90, 90, 90), font=font
        )
        cells.append(cell)
    rows = (len(cells) + COLUMNS - 1) // COLUMNS
    sheet = Image.new(
        "RGB", (COLUMNS * (CELL_WIDTH + 10) + 10, 50 + rows * (CELL_WIDTH + 54)), (255, 255, 255)
    )
    ImageDraw.Draw(sheet).text((12, 12), title, fill=(0, 0, 0), font=title_font)
    for i, cell in enumerate(cells):
        sheet.paste(cell, (10 + (i % COLUMNS) * (CELL_WIDTH + 10), 50 + (i // COLUMNS) * (CELL_WIDTH + 54)))
    return sheet


def render_frame(
    item: Item, progress: float, size: tuple[int, int], output_format: OutputFormat
) -> NDArray[np.float32]:
    assert item.motion is not None and item.canvas is not None
    window = window_at(item.motion, progress)
    left, top, right, bottom = window_rect(window, item.fit, output_format)
    k = item.canvas.shape[1] / item.fit.canvas_width
    sx = size[0] / ((right - left) * k)
    sy = size[1] / ((bottom - top) * k)
    matrix = np.array([[sx, 0, -left * k * sx], [0, sy, -top * k * sy]], dtype=np.float64)
    frame = cv2.warpAffine(item.canvas, matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return frame.astype(np.float32)


def write_video(items: list[Item], path: Path, output_format: OutputFormat, duration: float) -> None:
    ffmpeg = shutil.which("ffmpeg") or str(
        Path(__file__).resolve().parents[1] / "vendor/ffmpeg/bin/ffmpeg.exe"
    )
    size = (960, 540) if output_format is OutputFormat.HORIZONTAL else (540, 960)
    total = duration * len(items)
    half = min(CROSSFADE_S, duration / 2) / 2
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{size[0]}x{size[1]}",
    ]
    cmd += [
        "-r",
        str(FPS),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert process.stdin is not None
    for n in range(round(total * FPS)):
        t = n / FPS
        frame = np.zeros((size[1], size[0], 3), dtype=np.float32)
        for i, item in enumerate(items):
            start = i * duration - (half if i > 0 else 0)
            end = (i + 1) * duration + (half if i < len(items) - 1 else 0)
            if not start <= t < end:
                continue
            opacity = 1.0
            if i > 0 and t < i * duration + half:
                opacity = (t - (i * duration - half)) / (2 * half)
            if i < len(items) - 1 and t > (i + 1) * duration - half:
                opacity = ((i + 1) * duration + half - t) / (2 * half)
            frame += opacity * render_frame(item, (t - start) / (end - start), size, output_format)
        black = 1.0 - min(1.0, t / FADE_IN_S, (total - t) / FADE_OUT_S)
        frame *= 1.0 - max(0.0, black)
        process.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise SystemExit("ffmpeg ha fallat")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full de contactes dels moviments (fita F1).")
    parser.add_argument("folder", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="PNG de sortida")
    parser.add_argument("--video", type=Path, default=None, help="MP4 de mostra (opcional)")
    parser.add_argument("--vertical", action="store_true")
    parser.add_argument("--intensitat", choices=sorted(INTENSITIES), default="mitjana")
    parser.add_argument("--llavor", type=int, default=1)
    parser.add_argument("--durada", type=float, default=2.0, help="Segons per foto")
    parser.add_argument(
        "--zoom", type=float, default=None, help="Zoom per foto en %% (substitueix la intensitat)"
    )
    parser.add_argument("--desplacament", type=float, default=None, help="Desplaçament per foto en %%")
    args = parser.parse_args(argv)

    output_format = OutputFormat.VERTICAL if args.vertical else OutputFormat.HORIZONTAL
    items = load_items(args.folder, output_format)
    if not items:
        print("No s'ha trobat cap foto", file=sys.stderr)
        return 1
    preset = INTENSITY_PRESETS[INTENSITIES[args.intensitat]]
    amounts = MotionAmounts(
        preset.zoom if args.zoom is None else args.zoom / 100,
        preset.pan if args.desplacament is None else args.desplacament / 100,
    )
    assign_motions(items, output_format, amounts, args.llavor, args.durada)
    for item in items:
        item.canvas = build_canvas(item)
    format_name = "vertical" if args.vertical else "horitzontal"
    title = (
        f"Moviments · {len(items)} fotos de {args.durada:g} s · format {format_name} · "
        f"zoom {amounts.zoom * 100:g} % · desplaçament {amounts.pan * 100:g} % · llavor {args.llavor} · "
        "verd = inici, vermell = final"
    )
    contact_sheet(items, output_format, title).save(args.output)
    print(f"Full de contactes: {args.output}")
    if args.video is not None:
        write_video(items, args.video, output_format, args.durada)
        print(f"Vídeo de mostra: {args.video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
