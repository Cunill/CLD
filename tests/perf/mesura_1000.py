"""B15: 1,000 synthetic photos of 24 MP. Measures the import with thumbnails and the peak memory of
an export, each in a process of its own (so one measure does not inflate the other).

    uv run python -m tests.perf.mesura_1000 generar <carpeta> [--fotos 1000]
    uv run python -m tests.perf.mesura_1000 importar <carpeta>
    uv run python -m tests.perf.mesura_1000 exportar <carpeta> <video.mp4> [--fotos N]

Each command prints one line of JSON. tests/perf/test_thousand_photos.py runs them; the figures go
to docs/RENDIMENT.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 6000, 4000
"""24 MP, the size of a common camera."""
HEIC_SHARE = 20
"""One photo in 20 is HEIC (a phone): it cannot be decoded at a reduced size, unlike JPEG."""


def synthetic_photo(seed: int) -> np.ndarray:
    """Gradients and texture: compresses like a photo (a few MB at 24 MP)."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)[:, None]
    image = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
    image[..., 0] = 40 + 150 * x
    image[..., 1] = 90 + 110 * y
    image[..., 2] = 30 + 60 * (x + y)
    image += rng.integers(0, 16, size=(HEIGHT, WIDTH, 1), dtype=np.uint8)
    return image


def generate(folder: Path, count: int) -> list[Path]:
    """`count` files from four bases (three JPEG, one HEIC). The copies are hard links when the
    disk allows it: the program identifies photos by path, so each one is decoded on its own."""
    import pillow_heif

    pillow_heif.register_heif_opener()
    bases_dir = folder / "bases"
    bases_dir.mkdir(parents=True, exist_ok=True)
    bases: list[Path] = []
    for seed in range(3):
        path = bases_dir / f"camera_{seed}.jpg"
        if not path.exists():
            Image.fromarray(synthetic_photo(seed)).save(path, quality=90)
        bases.append(path)
    heic = bases_dir / "mobil.heic"
    if not heic.exists():
        Image.fromarray(synthetic_photo(9)).save(heic, "HEIF", quality=80)
    photos = folder / "fotos"
    photos.mkdir(exist_ok=True)
    paths: list[Path] = []
    for i in range(count):
        base = heic if i % HEIC_SHARE == HEIC_SHARE - 1 else bases[i % len(bases)]
        path = photos / f"foto_{i:04d}{base.suffix}"
        if not path.exists():
            try:
                os.link(base, path)
            except OSError:
                shutil.copyfile(base, path)
        paths.append(path)
    return paths


def peak_memory_bytes() -> int:
    """Peak resident memory of this process (Windows: peak working set)."""
    if sys.platform == "win32":
        import ctypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        # Types declared: without them ctypes passes the 64-bit process handle as a 32-bit int.
        current = kernel32.GetCurrentProcess
        current.restype = ctypes.c_void_p
        current.argtypes = []
        info = kernel32.K32GetProcessMemoryInfo
        info.restype = ctypes.c_int
        info.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
        if not info(current(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        return int(counters.PeakWorkingSetSize)
    import resource

    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def children_peak_memory_bytes() -> int | None:
    """Peak of the largest finished child (FFmpeg); not available on Windows."""
    if sys.platform == "win32":
        return None
    import resource

    return int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss) * 1024


def measure_import(folder: Path) -> dict[str, object]:
    """What the window does: read the headers, add the photos (motions drawn) and ask for every
    thumbnail. The clock stops when the last thumbnail arrives."""
    from passimaker.images import CachedImageSource
    from passimaker.importer import import_paths, photo_from_candidate, sort_candidates
    from passimaker.model import ProjectController
    from passimaker.model.commands import AddPhotos
    from passimaker.thumbs import Priority, ThumbnailService

    lock = threading.Lock()
    arrived = threading.Event()
    received: dict[str, bool] = {}
    expected = 0

    def collect(photo_id: str, image: object) -> None:
        with lock:
            received[photo_id] = image is not None
            if expected and len(received) >= expected:
                arrived.set()

    with tempfile.TemporaryDirectory(prefix="passimaker-mesura-") as cache:
        start = time.perf_counter()
        result = import_paths([folder / "fotos"])
        headers_s = time.perf_counter() - start
        controller = ProjectController()
        output = controller.project.output_format
        photos = tuple(
            photo_from_candidate(c, f"p{i:05d}", output)
            for i, c in enumerate(sort_candidates(result.candidates))
        )
        controller.execute(AddPhotos(photos, None))
        added_s = time.perf_counter() - start
        service = ThumbnailService(Path(cache) / "thumbs", CachedImageSource())
        try:
            expected = len(photos)
            for i, photo in enumerate(controller.project.photos):
                service.request_thumbnail(photo, Priority.VISIBLE if i < 40 else Priority.NORMAL, collect)
            arrived.wait(600)
            total_s = time.perf_counter() - start
        finally:
            service.close()
    return {
        "fotos": len(photos),
        "errors": len(result.failures),
        "miniatures": sum(received.values()),
        "capcaleres_s": round(headers_s, 2),
        "afegides_s": round(added_s, 2),
        "total_s": round(total_s, 2),
        "memoria_max_mb": round(peak_memory_bytes() / 2**20),
    }


def measure_export(folder: Path, video: Path, count: int | None) -> dict[str, object]:
    """A project made from the photos (1 s each, the shortest) and exported; memory is sampled while
    the frames are written."""
    from passimaker import cli
    from passimaker.export import ExportStatus, export_project

    source = folder / "fotos"
    if count is not None:
        source = folder / f"fotos_{count}"
        source.mkdir(exist_ok=True)
        for path in sorted((folder / "fotos").iterdir())[:count]:
            target = source / path.name
            if not target.exists():
                try:
                    os.link(path, target)
                except OSError:
                    shutil.copyfile(path, target)
    project = cli.new_project(source, (), name="mil", seed=1)
    project = replace(project, default_duration_s=1.0, crossfade_s=0.5)
    start = time.perf_counter()
    result = export_project(project, video)
    elapsed = time.perf_counter() - start
    return {
        "fotos": len(project.photos),
        "estat": result.status.value,
        "error": result.reason_key,
        "durada_video_s": round(result.duration_s, 1),
        "temps_s": round(elapsed, 1),
        "vegades_la_durada": round(elapsed / result.duration_s, 2)
        if result.status is ExportStatus.DONE
        else None,
        "memoria_max_mb": round(peak_memory_bytes() / 2**20),
        "ffmpeg_memoria_max_mb": (
            round(peak / 2**20) if (peak := children_peak_memory_bytes()) is not None else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesura_1000")
    sub = parser.add_subparsers(dest="ordre", required=True)
    gen = sub.add_parser("generar")
    gen.add_argument("carpeta", type=Path)
    gen.add_argument("--fotos", type=int, default=1000)
    imp = sub.add_parser("importar")
    imp.add_argument("carpeta", type=Path)
    exp = sub.add_parser("exportar")
    exp.add_argument("carpeta", type=Path)
    exp.add_argument("video", type=Path)
    exp.add_argument("--fotos", type=int, default=None)
    args = parser.parse_args(argv)
    if args.ordre == "generar":
        start = time.perf_counter()
        paths = generate(args.carpeta, args.fotos)
        report: dict[str, object] = {"fotos": len(paths), "temps_s": round(time.perf_counter() - start, 1)}
    elif args.ordre == "importar":
        report = measure_import(args.carpeta)
    else:
        report = measure_export(args.carpeta, args.video, args.fotos)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
