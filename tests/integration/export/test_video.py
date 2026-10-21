"""B9: the exported MP4 (20 test photos + 2 songs), checked with ffprobe and frame by frame."""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from passimaker.export import ExportResult, ExportStatus, export_project
from passimaker.ffmpeg import extract_frames, open_encoder
from passimaker.images import CachedImageSource
from passimaker.model import OutputFormat, Project, ResolvedFit
from passimaker.render import Compositor
from passimaker.timeline import Timeline, compute_timeline, query
from tests.integration.export.conftest import (
    ALL_PHOTOS,
    ARTEFACTS,
    ProgressLog,
    ffprobe,
    iter_frames,
    magenta_pixels,
    make_project,
    psnr,
    top_level_boxes,
)

pytestmark = pytest.mark.lent

MIN_PSNR_DB = 35.0
EDGE_PX = 2
MIN_EDGE_MEAN = 40
"""An edge line of a Fill photo darker than this on average is a black strip (test photos: > 80)."""


@dataclass(frozen=True, slots=True)
class Exported:
    project: Project
    timeline: Timeline
    video: Path
    result: ExportResult
    progress: ProgressLog
    elapsed_s: float


def _export(project: Project, video: Path) -> Exported:
    video.parent.mkdir(parents=True, exist_ok=True)
    log = ProgressLog()
    started = time.monotonic()
    result = export_project(project, video, progress=log, sentinel=True)
    elapsed = time.monotonic() - started
    return Exported(project, compute_timeline(project), video, result, log, elapsed)


@pytest.fixture(scope="module")
def horizontal(fixture_files: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> Exported:
    """20 photos and 2 songs, exported in sentinel mode to a folder and name with accents."""
    base = tmp_path_factory.mktemp("exportacio")
    project = make_project(fixture_files, base / "fotos", ALL_PHOTOS, ("tone_440.mp3", "tone_660.m4a"))
    exported = _export(project, base / "vídeos d'àvia" / "passi de l'estiu ñ.mp4")
    fps = exported.timeline.total_frames / exported.elapsed_s
    frames, seconds = exported.timeline.total_frames, exported.elapsed_s
    line = f"{frames} imatges 1920x1080 en {seconds:.1f} s: {fps:.1f} imatges/s"
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    (ARTEFACTS / "velocitat.txt").write_text(line + "\n", encoding="utf-8")
    print(f"\nExportació: {line}")
    return exported


@pytest.fixture(scope="module")
def vertical(fixture_files: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> Exported:
    """5 photos, vertical format, no music."""
    base = tmp_path_factory.mktemp("vertical")
    names = ("ratio_9x16.jpg", "ratio_4x3.jpg", "ratio_3x4.jpg", "pano_3x1.jpg", "photo.heic")
    project = make_project(fixture_files, base / "fotos", names, output_format=OutputFormat.VERTICAL)
    return _export(project, base / "vertical.mp4")


def test_the_export_succeeds_and_leaves_only_the_video(horizontal: Exported) -> None:
    assert horizontal.result.status is ExportStatus.DONE, horizontal.result
    assert horizontal.result.reason_key is None
    assert list(horizontal.video.parent.iterdir()) == [horizontal.video]
    assert horizontal.result.size_bytes == horizontal.video.stat().st_size > 0
    expected = horizontal.timeline.total_frames / horizontal.timeline.fps
    assert horizontal.result.duration_s == pytest.approx(expected)


def test_the_video_has_the_specified_format(horizontal: Exported) -> None:
    info = ffprobe(horizontal.video)
    video, audio = info.video, info.audio
    assert video["codec_name"] == "h264"
    assert video["profile"] == "High"
    assert (video["width"], video["height"]) == (1920, 1080)
    assert video["r_frame_rate"] == "30/1" and video["avg_frame_rate"] == "30/1"
    assert video["pix_fmt"] == "yuv420p"
    assert video["color_space"] == video["color_transfer"] == video["color_primaries"] == "bt709"
    assert video.get("color_range") == "tv"
    assert audio is not None
    assert audio["codec_name"] == "aac"
    assert audio["sample_rate"] == "48000" and audio["channels"] == 2
    boxes = top_level_boxes(horizontal.video)
    assert boxes.index("moov") < boxes.index("mdat"), boxes  # faststart


def test_the_duration_is_the_timeline_one(horizontal: Exported) -> None:
    info = ffprobe(horizontal.video)
    frames = int(str(info.video["nb_frames"]))
    assert abs(frames - horizontal.timeline.total_frames) <= 1
    assert horizontal.timeline.total_frames > 20 * 30  # 20 photos of 2 s minus the crossfades
    audio_s = float(str(info.audio["duration"])) if info.audio else 0.0
    assert audio_s == pytest.approx(horizontal.result.duration_s, abs=1 / 30 + 0.025)  # + AAC frame


def test_no_magenta_and_no_black_strip_on_fill_photos(horizontal: Exported) -> None:
    """Every frame of the video: no pixel outside the photos (sentinel mode), and the photos in
    Fill mode reach the four edges whenever they are alone on screen."""
    fits = {p.id: p.motion.resolved_fit for p in horizontal.project.photos}
    compositor = Compositor(horizontal.project, horizontal.timeline, CachedImageSource())
    magenta: list[tuple[int, int]] = []
    strips: list[tuple[int, str]] = []
    count = 0
    for n, frame in enumerate(iter_frames(horizontal.video, 1920, 1080)):
        count += 1
        if found := magenta_pixels(frame, compositor.frame_at(n / 30, 1920, 1080)):
            magenta.append((n, found))
        visibles = query(horizontal.timeline, n / 30)
        layers = visibles.layers
        alone_fill = (
            len(layers) == 1 and layers[0].opacity >= 1.0 and fits[layers[0].photo_id] is ResolvedFit.FILL
        )
        if alone_fill and visibles.black_level <= 0.0:
            edges = {
                "dalt": frame[:EDGE_PX],
                "baix": frame[-EDGE_PX:],
                "esquerra": frame[:, :EDGE_PX],
                "dreta": frame[:, -EDGE_PX:],
            }
            strips += [(n, side) for side, line in edges.items() if line.mean() < MIN_EDGE_MEAN]
    assert count == horizontal.timeline.total_frames
    assert magenta == []
    assert strips == []
    assert any(fit is ResolvedFit.FILL for fit in fits.values())


def test_the_magenta_check_sees_a_thin_strip_after_compression(tmp_path: Path) -> None:
    """Control: a 1-pixel magenta line survives H.264 4:2:0 and is detected, over a photo-like
    background and over black (what the compositor draws outside the photo without sentinel)."""
    reference = np.full((1080, 1920, 3), (120, 160, 110), dtype=np.uint8)
    reference[:, 1200:] = 0
    frame = reference.copy()
    frame[:, 700] = (255, 0, 255)
    frame[:, 1501] = (255, 0, 255)
    frame[333] = (255, 0, 255)
    video = tmp_path / "control.mp4"
    writer = open_encoder(video, 1920, 1080, None)
    for _ in range(3):
        writer.write(frame)
    writer.close()
    decoded = next(iter_frames(video, 1920, 1080))
    assert magenta_pixels(decoded, reference) >= 1080 + 1080 + 1900
    assert magenta_pixels(decoded, decoded) == 0


def test_frames_match_the_compositor(horizontal: Exported) -> None:
    """10 frames read back from the MP4 against the compositor (PSNR ≥ 35 dB)."""
    total = horizontal.timeline.total_frames
    indices = [round(i * (total - 1) / 9) for i in range(10)]
    slot = horizontal.timeline.slots[3]  # one crossfade in the middle
    indices[4] = round((slot.fade_out.start + slot.fade_out.end) / 2 * 30) if slot.fade_out else indices[4]
    decoded = extract_frames(horizontal.video, [(n + 0.5) / 30 for n in indices])
    compositor = Compositor(horizontal.project, horizontal.timeline, CachedImageSource())
    scores = {
        n: psnr(frame, compositor.frame_at(n / 30, 1920, 1080, sentinel=True))
        for n, frame in zip(indices, decoded, strict=True)
    }
    assert min(scores.values()) >= MIN_PSNR_DB, scores


def test_progress_always_advances_with_remaining_time(horizontal: Exported) -> None:
    calls = horizontal.progress.calls
    fractions = [f for f, _ in calls]
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert all(b >= a for a, b in itertools.pairwise(fractions))
    assert len(calls) >= 10
    later = [r for f, r in calls if f >= 0.25]
    assert later and all(r is not None and r >= 0 for r in later)
    assert calls[-1][1] == 0.0


def test_vertical_video(vertical: Exported) -> None:
    assert vertical.result.status is ExportStatus.DONE, vertical.result
    info = ffprobe(vertical.video)
    assert (info.video["width"], info.video["height"]) == (1080, 1920)
    frames = int(str(info.video["nb_frames"]))
    assert abs(frames - vertical.timeline.total_frames) <= 1
    assert info.audio is not None  # silent track: every video has sound (same output for every player)
    compositor = Compositor(vertical.project, vertical.timeline, CachedImageSource())
    for n, frame in enumerate(iter_frames(vertical.video, 1080, 1920)):
        if n % 3 == 0:
            assert magenta_pixels(frame, compositor.frame_at(n / 30, 1080, 1920)) == 0, n
