"""Sample video of the CI (block B9): 10 test photos and 2 songs, 20 s, made with the two commands.

    uv run python tools/mostra.py <output_folder>

Writes <output_folder>/mostra.passimaker and <output_folder>/mostra.mp4 exactly as a user would:
passimaker-nou with the default values, then passimaker-render.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.generate import generate_all  # noqa: E402

from passimaker import cli  # noqa: E402

PHOTOS = (
    "ratio_4x3.jpg",
    "ratio_9x16.jpg",
    "pano_3x1.jpg",
    "ratio_16x9.jpg",
    "photo.heic",
    "tiny_320x240.jpg",
    "ratio_3x4.jpg",
    "orient_6.jpg",
    "ratio_1x1.jpg",
    "huge_8000x6000.jpg",
)
SONGS = ("tone_440.mp3", "tone_660.m4a")


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else ROOT / "tests" / "_artefactes" / "mostra"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="passimaker-mostra-") as work:
        files = generate_all(Path(work) / "dades")
        photos = Path(work) / "fotos"
        photos.mkdir()
        for name in PHOTOS:
            (photos / name).write_bytes(files[name].read_bytes())
        project = out / "mostra.passimaker"
        songs = [str(files[name]) for name in SONGS]
        code = cli.main_new([str(photos), *songs, "-o", str(project), "--llavor", "1"])
        if code != cli.EXIT_OK:
            return code
        return cli.main_render([str(project), str(out / "mostra.mp4")])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
