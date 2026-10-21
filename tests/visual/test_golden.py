"""B6 · Golden images: approved frames that must not change by accident (PSNR >= 40 dB).

The reference images are in tests/golden/render. They are only rewritten on purpose, with the
user's approval:

    PASSIMAKER_REGENERAR_GOLDEN=1 uv run pytest tests/visual/test_golden.py

Every run also writes the current frames to tests/_artefactes/render/golden (a CI artefact).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from passimaker.model.types import FitMode, MotionType, OutputFormat, Project
from passimaker.timeline import Timeline
from tests.visual.helpers import ARTEFACTS, build_project, compositor_for, photo, psnr

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "render"
REGENERATE = os.environ.get("PASSIMAKER_REGENERAR_GOLDEN") == "1"
MIN_PSNR_DB = 40.0


def _horizontal() -> Project:
    photos = [
        photo("g_4x3", 4000, 3000),
        photo("g_3x2", 3000, 2000),
        photo("g_3x4", 3000, 4000),
        photo("g_pano", 6000, 2000),
        photo("g_pano_black", 6000, 2000),
        photo("g_tiny", 320, 240),
        photo("g_end", 4000, 3000),  # the last photo is always inside the fade to black
    ]
    motions = {
        "g_4x3": MotionType.ZOOM_IN,
        "g_3x2": MotionType.PAN_RIGHT,
        "g_3x4": MotionType.ZOOM_OUT,
        "g_pano": MotionType.ZOOM_IN,
        "g_pano_black": MotionType.NONE,
    }
    return build_project(photos, motions=motions, fits={"g_pano_black": FitMode.BLACK}, seed=5)


def _vertical() -> Project:
    photos = [photo("g_4x3", 4000, 3000), photo("g_3x4", 3000, 4000), photo("g_9x16", 1080, 1920)]
    motions = {"g_4x3": MotionType.ZOOM_IN, "g_3x4": MotionType.PAN_UP, "g_9x16": MotionType.COMBINED}
    return build_project(photos, OutputFormat.VERTICAL, motions=motions, seed=5)


def _alone(index: int, where: float) -> Callable[[Timeline], float]:
    """A time where photo `index` is seen alone and without black: where = 0 (first) ... 1 (last)."""

    def pick(timeline: Timeline) -> float:
        slot = timeline.slots[index]
        first = slot.visible_start if slot.fade_in is None else slot.fade_in.end
        last = slot.visible_end if slot.fade_out is None else slot.fade_out.start
        if timeline.fade_from_black is not None:
            first = max(first, timeline.fade_from_black.end)
        if timeline.fade_to_black is not None:
            last = min(last, timeline.fade_to_black.start)
        assert first < last
        return first + (last - first) * where

    return pick


def _crossfade(index: int) -> Callable[[Timeline], float]:
    return lambda timeline: timeline.slots[index].slot_start


@dataclass(frozen=True)
class Case:
    name: str
    project: Callable[[], Project]
    time: Callable[[Timeline], float]


CASES = (
    Case("h01_omplir_apropar_inici", _horizontal, _alone(0, 0.0)),
    Case("h02_omplir_apropar_final", _horizontal, _alone(0, 1.0)),
    Case("h03_omplir_desplacar_mig", _horizontal, _alone(1, 0.5)),
    Case("h04_fosa_encadenada", _horizontal, _crossfade(2)),
    Case("h05_difuminat_vertical", _horizontal, _alone(2, 0.5)),
    Case("h06_difuminat_panoramica", _horizontal, _alone(3, 0.5)),
    Case("h07_negre_panoramica", _horizontal, _alone(4, 0.5)),
    Case("h08_foto_petita", _horizontal, _alone(5, 0.0)),
    Case("h09_fosa_des_de_negre", _horizontal, lambda timeline: 0.4),
    Case("h10_fosa_a_negre", _horizontal, lambda timeline: timeline.total_duration_s - 0.6),
    Case("v11_difuminat_horitzontal", _vertical, _alone(0, 0.5)),
    Case("v12_omplir_desplacar_amunt", _vertical, _alone(1, 0.5)),
)


def _render(case: Case) -> NDArray[np.uint8]:
    project = case.project()
    compositor, timeline = compositor_for(project)
    size = (640, 360) if project.output_format is OutputFormat.HORIZONTAL else (360, 640)
    return compositor.frame_at(case.time(timeline), *size)


def test_there_are_twelve_cases() -> None:
    assert len({case.name for case in CASES}) == 12


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_golden(case: Case) -> None:
    frame = _render(case)
    current = ARTEFACTS / "golden" / f"{case.name}.png"
    current.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame).save(current)
    reference = GOLDEN / f"{case.name}.png"
    if REGENERATE:
        reference.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(frame).save(reference)
        return
    assert reference.exists(), f"Falta la imatge de referència {reference.name} (vegeu el docstring)"
    with Image.open(reference) as image:
        expected = np.asarray(image.convert("RGB"), dtype=np.uint8)
    assert expected.shape == frame.shape
    assert psnr(frame, expected) >= MIN_PSNR_DB
