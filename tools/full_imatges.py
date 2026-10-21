"""Full d'imatges del compositor (revisió del bloc B6) i, opcionalment, un vídeo de mostra sense so.

Per a cada foto d'una carpeta dibuixa tres imatges del passi tal com sortiran al vídeo (amb el
compositor real del programa): l'inici del moviment, el mig i el final, i una quarta amb la fosa
encadenada cap a la foto següent. Serveix per revisar les fotos verticals amb fons difuminat, les
panoràmiques, les fotos petites i les foses.

Ús:
    uv run python tools/full_imatges.py <carpeta> -o full.png [--video mostra.mp4] [--vertical]
        [--llavor N] [--durada 2] [--sentinella] [--amplada 400]

Per fer-lo amb les fotos de prova:
    uv run python -m tests.fixtures.generate tests/_generated
    uv run python tools/full_imatges.py tests/_generated -o full.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from passimaker.images import CachedImageSource
from passimaker.importer import import_paths
from passimaker.model.commands import AddPhotos, SetDefaultDuration
from passimaker.model.controller import ProjectController
from passimaker.model.types import MotionType, OutputFormat, Photo, Project, ResolvedFit
from passimaker.render import Compositor
from passimaker.timeline import Interval, PhotoSlot, Timeline, compute_timeline, query

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
FITS = {ResolvedFit.FILL: "Omplir", ResolvedFit.BLUR: "Fons difuminat", ResolvedFit.BLACK: "Fons negre"}
COLUMNS = ("Inici", "Mig", "Final", "Fosa cap a la següent")
FONT_CANDIDATES = ("DejaVuSans.ttf", "segoeui.ttf", "arial.ttf")
BACKGROUND = (245, 245, 240)
GAP = 8
LABEL_HEIGHT = 26


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A font with Catalan characters (the bundled default lacks "ç")."""
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def build_project(folder: Path, output_format: OutputFormat, seed: int, duration_s: float) -> Project:
    """Imports the folder like the program does (order, fits and motions included)."""
    result = import_paths([folder])
    for failure in result.failures:
        print(f"No s'ha pogut afegir {failure.path.name}: {failure.reason.value}", file=sys.stderr)
    photos = tuple(
        Photo(
            f"f{i:04d}",
            c.path,
            None,
            c.width,
            c.height,
            exif_orientation=c.exif_orientation,
            capture_time=c.capture_time,
        )
        for i, c in enumerate(result.candidates)
    )
    controller = ProjectController(Project(output_format=output_format, seed=seed))
    controller.execute(SetDefaultDuration(duration_s))
    controller.execute(AddPhotos(photos))
    return controller.project


def sample_times(slot: PhotoSlot, timeline: Timeline) -> tuple[float, float, float, float | None]:
    """First, middle and last instant where the photo is seen alone (fully opaque), and the middle
    of the crossfade to the next photo. Inside the black fades, no earlier or later than halfway."""
    first = slot.visible_start if slot.fade_in is None else slot.fade_in.end
    last = slot.visible_end if slot.fade_out is None else slot.fade_out.start
    middle = (first + last) / 2
    if timeline.fade_from_black is not None:
        first = min(middle, max(first, sum(_bounds(timeline.fade_from_black)) / 2))
    if timeline.fade_to_black is not None:
        last = max(middle, min(last, sum(_bounds(timeline.fade_to_black)) / 2))
    crossfade = None if slot.fade_out is None else sum(_bounds(slot.fade_out)) / 2
    return first, middle, last, crossfade


def _bounds(interval: Interval) -> tuple[float, float]:
    return interval.start, interval.end


def contact_sheet(
    project: Project,
    timeline: Timeline,
    compositor: Compositor,
    cell_width: int,
    *,
    sentinel: bool = False,
) -> Image.Image:
    out_w, out_h = project.output_format.size
    cell_height = round(cell_width * out_h / out_w)
    font, title_font = load_font(14), load_font(19)
    photos = {p.id: p for p in project.photos}
    row_height = LABEL_HEIGHT + cell_height + GAP
    width = GAP + len(COLUMNS) * (cell_width + GAP)
    height = 40 + LABEL_HEIGHT + row_height * len(timeline.slots)
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    format_name = "vertical" if project.output_format is OutputFormat.VERTICAL else "horitzontal"
    title = f"Compositor · {len(timeline.slots)} fotos · format {format_name} · llavor {project.seed}" + (
        " · mode sentinella (magenta = fora de la imatge)" if sentinel else ""
    )
    draw.text((GAP, 10), title, fill=(20, 20, 20), font=title_font)
    for column, label in enumerate(COLUMNS):
        draw.text((GAP + column * (cell_width + GAP), 40), label, fill=(90, 90, 90), font=font)
    for row, slot in enumerate(timeline.slots):
        top = 40 + LABEL_HEIGHT + row * row_height
        photo = photos[slot.photo_id]
        label = (
            f"{slot.index + 1}. {photo.path.name}  ·  {photo.width}×{photo.height}  ·  "
            f"{FITS[photo.motion.resolved_fit]}  ·  {LABELS[photo.motion.type]}"
        )
        draw.text((GAP, top + 4), label, fill=(20, 20, 20), font=font)
        for column, t in enumerate(sample_times(slot, timeline)):
            if t is None:
                continue
            frame = _without_black_fades(compositor, timeline, t, cell_width, cell_height, sentinel)
            sheet.paste(Image.fromarray(frame), (GAP + column * (cell_width + GAP), top + LABEL_HEIGHT))
    return sheet


def _without_black_fades(
    compositor: Compositor, timeline: Timeline, t: float, width: int, height: int, sentinel: bool
) -> NDArray[np.uint8]:
    """The frame at t; inside the black fades, the same frame brightened back (for review only)."""
    frame = compositor.frame_at(t, width, height, sentinel=sentinel)
    level = query(timeline, t).black_level
    if level <= 0.0 or level >= 0.999:
        return frame
    restored = frame.astype(np.float32) / (1.0 - level)
    return np.clip(restored, 0, 255).astype(np.uint8)


def write_video(
    timeline: Timeline, compositor: Compositor, dest: Path, size: tuple[int, int], sentinel: bool
) -> None:
    """Silent MP4 of the whole show, through the program's FFmpeg bridge."""
    from passimaker.ffmpeg import open_encoder

    writer = open_encoder(dest, size[0], size[1], None)
    try:
        for n in range(timeline.total_frames):
            writer.write(compositor.frame_at(n / timeline.fps, size[0], size[1], sentinel=sentinel))
    except BaseException:
        writer.abort()
        raise
    writer.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full d'imatges del compositor (bloc B6).")
    parser.add_argument("folder", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="PNG de sortida")
    parser.add_argument("--video", type=Path, default=None, help="MP4 de mostra sense so (opcional)")
    parser.add_argument("--vertical", action="store_true")
    parser.add_argument("--llavor", type=int, default=1)
    parser.add_argument("--durada", type=float, default=2.0, help="Segons per foto")
    parser.add_argument("--amplada", type=int, default=400, help="Amplada de cada imatge del full")
    parser.add_argument("--sentinella", action="store_true", help="Magenta fora de la imatge")
    parser.add_argument("--mida-video", default="1920x1080", help="Mida del vídeo (horitzontal)")
    args = parser.parse_args(argv)

    output_format = OutputFormat.VERTICAL if args.vertical else OutputFormat.HORIZONTAL
    project = build_project(args.folder, output_format, args.llavor, args.durada)
    if not project.photos:
        print("No s'ha trobat cap foto", file=sys.stderr)
        return 1
    timeline = compute_timeline(project)
    source = CachedImageSource()
    try:
        compositor = Compositor(project, timeline, source)
        sheet = contact_sheet(project, timeline, compositor, args.amplada, sentinel=args.sentinella)
        sheet.save(args.output)
        print(f"Full d'imatges: {args.output}")
        if args.video is not None:
            width, height = (int(v) for v in args.mida_video.lower().split("x"))
            size = (height, width) if args.vertical else (width, height)
            write_video(timeline, compositor, args.video, size, args.sentinella)
            print(f"Vídeo de mostra: {args.video}")
    finally:
        source.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
