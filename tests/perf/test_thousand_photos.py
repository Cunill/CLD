"""B15: 1,000 synthetic photos of 24 MP (PLA, B15).

- Import with every thumbnail in less than 2 minutes.
- Peak memory while exporting under 1.5 GB (the program; FFmpeg is a process of its own).

Each measure runs in a process of its own (tests/perf/mesura_1000.py), so the memory of one does
not count in the other. Slow: the export of 1,000 photos (1 s each) takes about half an hour.
The figures are written to tests/_artefactes/rendiment/mil_fotos.txt and go to docs/RENDIMENT.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTEFACTS = ROOT / "tests" / "_artefactes" / "rendiment"
IMPORT_LIMIT_S = 120.0
EXPORT_MEMORY_LIMIT_MB = 1.5 * 1024


def _measure(*args: str, env: dict[str, str] | None = None) -> dict[str, object]:
    command = [sys.executable, "-m", "tests.perf.mesura_1000", *args]
    done = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True, env=env, timeout=7200
    )
    report: dict[str, object] = json.loads(done.stdout.strip().splitlines()[-1])
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    with (ARTEFACTS / "mil_fotos.txt").open("a", encoding="utf-8") as out:
        out.write(f"{args[0]}: {json.dumps(report, ensure_ascii=False)}\n")
    return report


@pytest.fixture(scope="module")
def thousand(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("mil")
    _measure("generar", str(folder))
    return folder


@pytest.mark.perf
def test_importing_a_thousand_photos_with_thumbnails(thousand: Path) -> None:
    report = _measure("importar", str(thousand))
    assert report["fotos"] == 1000 and report["miniatures"] == 1000
    assert float(str(report["total_s"])) < IMPORT_LIMIT_S


@pytest.mark.perf
def test_exporting_a_thousand_photos_stays_under_the_memory_limit(thousand: Path, tmp_path: Path) -> None:
    env = {**os.environ, "PASSIMAKER_CACHE": str(tmp_path / "cache")}
    report = _measure("exportar", str(thousand), str(tmp_path / "mil.mp4"), env=env)
    assert report["estat"] == "done", report
    assert float(str(report["memoria_max_mb"])) < EXPORT_MEMORY_LIMIT_MB
