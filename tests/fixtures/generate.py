"""Deterministic generator of test photos and audio.

Same inputs -> same bytes (on the same machine and library versions). Run directly to
inspect the files:

    uv run python -m tests.fixtures.generate <output_dir>

Photo content never contains magenta-like pixels: min(R - G, B - G) stays below
MAX_MAGENTA_EXCESS (green >= 100, red and blue <= 220), so the compositor's sentinel colour
(255, 0, 255) can only come from outside the photo, even after lossy compression.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import wave
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pillow_heif
from numpy.typing import NDArray
from PIL import ExifTags, Image, ImageDraw

MIN_GREEN = 100
MAX_MAGENTA_EXCESS = 150
TONE_AMPLITUDE = 0.25  # -12 dBFS
SAMPLE_RATE = 48000


@dataclass(frozen=True, slots=True)
class PhotoSpec:
    name: str
    width: int
    """Stored pixel width (before EXIF orientation)."""
    height: int
    orientation: int = 1
    capture_time: datetime | None = None
    kind: str = "jpeg"  # jpeg | png_alpha | png_gray16 | cmyk | heic

    @property
    def oriented_size(self) -> tuple[int, int]:
        """(width, height) after applying EXIF orientation."""
        return (self.height, self.width) if self.orientation in (5, 6, 7, 8) else (self.width, self.height)


@dataclass(frozen=True, slots=True)
class ToneSpec:
    name: str
    frequency: float
    duration_s: float


def _dt(day: int) -> datetime:
    return datetime(2024, 5, day, 10, 0, 0)


PHOTO_SPECS: tuple[PhotoSpec, ...] = (
    PhotoSpec("ratio_4x3.jpg", 1600, 1200, capture_time=_dt(1)),
    PhotoSpec("ratio_3x2.jpg", 1800, 1200, capture_time=_dt(2)),
    PhotoSpec("ratio_16x9.jpg", 1920, 1080, capture_time=_dt(3)),
    PhotoSpec("ratio_9x16.jpg", 1080, 1920, capture_time=_dt(4)),
    PhotoSpec("ratio_3x4.jpg", 1200, 1600, capture_time=_dt(5)),
    PhotoSpec("ratio_1x1.jpg", 1200, 1200, capture_time=_dt(6)),
    PhotoSpec("pano_3x1.jpg", 3600, 1200, capture_time=_dt(7)),
    PhotoSpec("tiny_320x240.jpg", 320, 240),
    PhotoSpec("huge_8000x6000.jpg", 8000, 6000, capture_time=_dt(8)),
    PhotoSpec("cmyk.jpg", 1200, 900, kind="cmyk"),
    PhotoSpec("alpha.png", 1000, 750, kind="png_alpha"),
    PhotoSpec("gray16.png", 1000, 750, kind="png_gray16"),
    PhotoSpec("photo.heic", 1200, 900, capture_time=_dt(9), kind="heic"),
    *(
        PhotoSpec(f"orient_{n}.jpg", *((400, 600) if n in (5, 6, 7, 8) else (600, 400)), orientation=n)
        for n in range(1, 9)
    ),
)

TONE_SPECS: tuple[ToneSpec, ...] = (
    ToneSpec("tone_440", 440.0, 8.0),
    ToneSpec("tone_660", 660.0, 6.0),
    ToneSpec("tone_880", 880.0, 10.0),
)
AUDIO_FORMATS: tuple[str, ...] = ("wav", "mp3", "m4a", "flac", "ogg")

BROKEN_FILES: tuple[str, ...] = ("corrupt.jpg", "not_an_image.jpg")

# Inverse of the transform that PIL.ImageOps.exif_transpose applies for each orientation.
_STORE_TRANSFORM: dict[int, Image.Transpose | None] = {
    1: None,
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_90,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_270,
}


def _seed(name: str) -> int:
    return zlib.crc32(name.encode("utf-8"))


def synthetic_rgb(width: int, height: int, seed: int) -> NDArray[np.uint8]:
    """Smooth gradients plus a grid of discs: textured enough to measure motion, never magenta."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    fx, fy = x / max(width - 1, 1), y / max(height - 1, 1)
    phase = rng.uniform(0, 2 * math.pi, size=3).astype(np.float32)
    r = 0.5 + 0.5 * np.sin(2 * math.pi * (fx * 1.3 + fy * 0.4) + phase[0])
    g = 0.5 + 0.5 * np.sin(2 * math.pi * (fx * 0.5 + fy * 1.1) + phase[1])
    b = 0.5 + 0.5 * np.sin(2 * math.pi * (fx * 0.9 - fy * 0.7) + phase[2])
    img = np.stack([40 + 180 * r, MIN_GREEN + 140 * g, 40 + 180 * b], axis=-1)
    cell = max(16, min(width, height) // 8)
    cy, cx = (y % cell) - cell / 2, (x % cell) - cell / 2
    disc = (cx * cx + cy * cy) < (cell * 0.3) ** 2
    img[disc] = img[disc] * 0.55 + np.array([20, MIN_GREEN + 40, 20], dtype=np.float32) * 0.45
    out = np.clip(img, 0, 255).astype(np.uint8)
    out[..., 1] = np.maximum(out[..., 1], MIN_GREEN)
    return out


def f_pattern(width: int, height: int) -> NDArray[np.uint8]:
    """Light background with a large dark asymmetric "F" (used to check orientation)."""
    img = Image.new("RGB", (width, height), (220, 225, 210))
    draw = ImageDraw.Draw(img)
    u = min(width, height) // 8
    left, top = width // 2 - 2 * u, height // 2 - 3 * u
    draw.rectangle((left, top, left + u, top + 6 * u), fill=(30, 70, 40))
    draw.rectangle((left, top, left + 4 * u, top + u), fill=(30, 70, 40))
    draw.rectangle((left, top + 2 * u + u // 2, left + 3 * u, top + 3 * u + u // 2), fill=(30, 70, 40))
    return np.asarray(img, dtype=np.uint8).copy()


def _synthetic_image(width: int, height: int, seed: int) -> Image.Image:
    """Large images are generated at 1/4 size and upscaled (much faster, still deterministic)."""
    if width * height <= 4_000_000:
        return Image.fromarray(synthetic_rgb(width, height, seed))
    small = Image.fromarray(synthetic_rgb(width // 4, height // 4, seed))
    return small.resize((width, height), Image.Resampling.BICUBIC)


def _exif(spec: PhotoSpec) -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = spec.orientation
    if spec.capture_time is not None:
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
        ifd[ExifTags.Base.DateTimeOriginal] = spec.capture_time.strftime("%Y:%m:%d %H:%M:%S")
    return exif


def _write_photo(spec: PhotoSpec, dest: Path) -> None:
    if spec.name.startswith("orient_"):
        upright_w, upright_h = spec.oriented_size
        img = Image.fromarray(f_pattern(upright_w, upright_h))
        transform = _STORE_TRANSFORM[spec.orientation]
        if transform is not None:
            img = img.transpose(transform)
        assert img.size == (spec.width, spec.height)
    else:
        img = _synthetic_image(spec.width, spec.height, _seed(spec.name))

    if spec.kind == "jpeg":
        img.save(dest, "JPEG", quality=90, exif=_exif(spec))
    elif spec.kind == "cmyk":
        img.convert("CMYK").save(dest, "JPEG", quality=90)
    elif spec.kind == "png_alpha":
        rgba = img.convert("RGBA")
        alpha = Image.new("L", img.size, 255)
        ImageDraw.Draw(alpha).ellipse((0, 0, img.size[0] // 2, img.size[1] // 2), fill=0)
        rgba.putalpha(alpha)
        rgba.save(dest, "PNG")
    elif spec.kind == "png_gray16":
        gray = np.asarray(img.convert("L"), dtype=np.uint16) * 257
        Image.fromarray(gray.astype(np.uint16)).save(dest, "PNG")
    elif spec.kind == "heic":
        pillow_heif.register_heif_opener()
        img.save(dest, "HEIF", quality=80, exif=_exif(spec).tobytes())
    else:
        raise ValueError(spec.kind)


def _write_broken(name: str, dest: Path, valid_jpeg: Path) -> None:
    if name == "corrupt.jpg":
        data = valid_jpeg.read_bytes()
        dest.write_bytes(data[: len(data) // 3] + bytes(range(256)) * 4)
    else:
        dest.write_text("Això no és una imatge.\n", encoding="utf-8")


def tone_samples(spec: ToneSpec) -> NDArray[np.int16]:
    n = round(spec.duration_s * SAMPLE_RATE)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    mono = TONE_AMPLITUDE * np.sin(2 * math.pi * spec.frequency * t)
    stereo = np.repeat(mono[:, None], 2, axis=1)
    return np.round(stereo * 32767).astype(np.int16)


def _write_wav(samples: NDArray[np.int16], dest: Path) -> None:
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples.tobytes())


_ENCODER_ARGS: dict[str, list[str]] = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
}


def find_ffmpeg() -> str:
    """Test-only locator (production code uses passi.ffmpeg.locate)."""
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    env = os.environ.get("PASSI_FFMPEG")
    candidates = [Path(env) / exe] if env else []
    root = Path(__file__).resolve().parents[2]
    candidates.append(root / "vendor" / "ffmpeg" / "bin" / exe)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    if found is None:
        raise FileNotFoundError("ffmpeg no trobat: executa tools/obtenir_ffmpeg")
    return found


def _encode(ffmpeg: str, src: Path, dest: Path, fmt: str) -> None:
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src)]
    cmd += ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact"]
    cmd += [*_ENCODER_ARGS[fmt], str(dest)]
    subprocess.run(cmd, check=True, capture_output=True)


def generate_all(dest: Path, *, include_audio: bool = True) -> dict[str, Path]:
    """Writes every fixture into dest and returns {file name: path}."""
    dest.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for spec in PHOTO_SPECS:
        path = dest / spec.name
        _write_photo(spec, path)
        files[spec.name] = path
    for name in BROKEN_FILES:
        path = dest / name
        _write_broken(name, path, files["ratio_4x3.jpg"])
        files[name] = path
    if include_audio:
        ffmpeg = find_ffmpeg()
        for spec in TONE_SPECS:
            wav = dest / f"{spec.name}.wav"
            _write_wav(tone_samples(spec), wav)
            files[wav.name] = wav
            for fmt in AUDIO_FORMATS[1:]:
                out = dest / f"{spec.name}.{fmt}"
                _encode(ffmpeg, wav, out, fmt)
                files[out.name] = out
    return files


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/_generated")
    for name in generate_all(target):
        print(name)
