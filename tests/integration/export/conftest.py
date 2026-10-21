"""Fixtures of the export tests (block B9): projects built like passimaker-nou, and video readers."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from passimaker import cli
from passimaker.common import RGBImage
from passimaker.export import CACHE_ENV_VAR
from passimaker.ffmpeg import locate
from passimaker.model import OutputFormat, Project

ARTEFACTS = Path(__file__).resolve().parents[3] / "tests" / "_artefactes" / "export"

ALL_PHOTOS: tuple[str, ...] = (
    "ratio_4x3.jpg",
    "ratio_3x2.jpg",
    "ratio_16x9.jpg",
    "ratio_9x16.jpg",
    "ratio_3x4.jpg",
    "ratio_1x1.jpg",
    "pano_3x1.jpg",
    "tiny_320x240.jpg",
    "huge_8000x6000.jpg",
    "cmyk.jpg",
    "gray16.png",
    "photo.heic",
    *(f"orient_{n}.jpg" for n in range(1, 9)),
)
"""The 20 test photos (alpha.png is left out: its transparent corner is black on purpose)."""

MAGENTA_RISE = 60
"""A pixel of the video is magenta when its magenta excess, min(R − G, B − G), is this much above
the same pixel of the compositor's normal frame (where anything outside the photo is black).
H.264 4:2:0 halves the colour of a 1-pixel line: over black it rises ~75 (control test); compression
noise on pinkish areas of the test photos rises up to ~52."""

MAGENTA_FLOOR = 40
"""...and the excess itself is above this (black is 0; test photos reach 120 only in magenta-ish areas)."""


@pytest.fixture(scope="session", autouse=True)
def _cache_in_temporary_folder(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """The audio cache of the exports goes to a temporary folder, not the user's."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CACHE_ENV_VAR, str(tmp_path_factory.mktemp("memoria_cau")))
        yield


def photo_folder(fixture_files: dict[str, Path], dest: Path, names: Sequence[str]) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(fixture_files[name], dest / name)
    return dest


def make_project(
    fixture_files: dict[str, Path],
    folder: Path,
    names: Sequence[str],
    music: Sequence[str] = (),
    *,
    output_format: OutputFormat = OutputFormat.HORIZONTAL,
    seed: int = 7,
) -> Project:
    """The project passimaker-nou would create (import, automatic order, motions drawn)."""
    photos = photo_folder(fixture_files, folder, names)
    songs = [fixture_files[name] for name in music]
    return cli.new_project(photos, songs, name=folder.name, output_format=output_format, seed=seed)


@dataclass(frozen=True, slots=True)
class Probe:
    video: dict[str, object]
    audio: dict[str, object] | None
    format: dict[str, object]


def ffprobe(path: Path) -> Probe:
    args = [str(locate().ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    data = json.loads(subprocess.run(args, capture_output=True, check=True).stdout)
    streams = data["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)
    return Probe(video, audio, data["format"])


def top_level_boxes(path: Path) -> list[str]:
    """Names of the top-level MP4 boxes, in file order (faststart: moov before mdat)."""
    names: list[str] = []
    with path.open("rb") as f:
        while header := f.read(8):
            size = int.from_bytes(header[:4], "big")
            names.append(header[4:8].decode("latin-1"))
            if size == 1:
                size = int.from_bytes(f.read(8), "big") - 8
            elif size == 0:
                break
            f.seek(size - 8, 1)
    return names


def iter_frames(path: Path, width: int, height: int) -> Iterator[RGBImage]:
    """Every frame of the video as RGB, in order (same colour conversion as ffmpeg.extract_frames)."""
    args = [str(locate().ffmpeg), "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0"]
    args += [
        "-vf",
        "scale=flags=accurate_rnd+full_chroma_int",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    size = width * height * 3
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        assert process.stdout is not None
        while len(data := process.stdout.read(size)) == size:
            yield np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)
        process.stdout.close()
        process.wait()


def magenta_excess(frame: RGBImage) -> np.ndarray:
    signed = frame.astype(np.int16)
    return np.minimum(signed[..., 0] - signed[..., 1], signed[..., 2] - signed[..., 1])


def magenta_pixels(frame: RGBImage, reference: RGBImage) -> int:
    """Pixels of a decoded sentinel-mode frame that are magenta where `reference` (the same
    instant drawn without sentinel) is not."""
    excess = magenta_excess(frame)
    rise = excess - magenta_excess(reference)
    return int(np.count_nonzero((rise > MAGENTA_RISE) & (excess > MAGENTA_FLOOR)))


def psnr(a: RGBImage, b: RGBImage) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(255.0**2 / mse)


class ProgressLog:
    """Records progress(fraction, remaining) calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float | None]] = []

    def __call__(self, fraction: float, remaining: float | None) -> None:
        self.calls.append((fraction, remaining))
