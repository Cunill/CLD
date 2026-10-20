"""B3 · Balance rules, distribution, determinism, draw again and manual motions (§1.5)."""

from __future__ import annotations

import itertools
import random
from collections import Counter

import pytest

from passi.model.types import (
    FitMode,
    Intensity,
    MotionMode,
    MotionType,
    OutputFormat,
    PhotoMotion,
    ResolvedFit,
)
from passi.motion import BASE_PROBABILITIES, draw_motions, option_of, rebuild_motions
from passi.motion.draw import Family
from tests.unit.motion.helpers import draw_sequence, request

FILL_SIZES = [(4000, 3000), (3000, 2000), (1920, 1080), (4032, 3024), (5000, 4000), (6000, 3376)]
PANS = (MotionType.PAN_LEFT, MotionType.PAN_RIGHT, MotionType.PAN_UP, MotionType.PAN_DOWN)


def fill_sizes(n: int, seed: int) -> list[tuple[int, int]]:
    rng = random.Random(seed)
    return [rng.choice(FILL_SIZES) for _ in range(n)]


def check_rules(motions: list[PhotoMotion]) -> None:
    options = [option_of(m) for m in motions]
    for a, b in itertools.pairwise(options):
        assert a != b, "regla 1: mateix tipus i direcció seguits"
    run = 1
    for a, b in itertools.pairwise(options):
        run = run + 1 if a.family is b.family else 1
        assert run <= 2 or a.family is Family.NONE, "regla 2: més de 2 de la mateixa família"
    for i in range(len(options) - 5):
        assert abs(sum(o.zoom for o in options[i : i + 6])) <= 2, f"regla 3 a la posició {i}"
    assert motions[0].type is MotionType.ZOOM_IN
    assert motions[-1].type is MotionType.ZOOM_OUT


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("intensity", list(Intensity))
def test_rules_hold_on_1000_photos(seed: int, intensity: Intensity) -> None:
    _, motions = draw_sequence(fill_sizes(1000, seed), seed=seed, intensity=intensity)
    check_rules(motions)


def test_rules_hold_in_vertical_format() -> None:
    sizes = [random.Random(i).choice([(3000, 4000), (2000, 3000), (1080, 1920)]) for i in range(1000)]
    _, motions = draw_sequence(sizes, seed=11, output_format=OutputFormat.VERTICAL)
    check_rules(motions)


def test_distribution_over_1000_photos_is_within_5_points() -> None:
    totals: Counter[str] = Counter()
    for seed in range(5):
        _, motions = draw_sequence(fill_sizes(1000, seed), seed=seed)
        totals.update("pans" if m.type in PANS else m.type.value for m in motions)
    measured = {k: 100 * v / 5000 for k, v in totals.items()}
    expected = {
        "zoom_in": 100 * BASE_PROBABILITIES[MotionType.ZOOM_IN],
        "zoom_out": 100 * BASE_PROBABILITIES[MotionType.ZOOM_OUT],
        "pans": 100 * sum(BASE_PROBABILITIES[t] for t in PANS),
        "combined": 100 * BASE_PROBABILITIES[MotionType.COMBINED],
    }
    for key, value in expected.items():
        assert abs(measured[key] - value) <= 5, f"{key}: {measured[key]:.1f} % (esperat {value:.0f} %)"


def test_pans_prefer_the_axis_with_room() -> None:
    # 4:3 in a 16:9 video: there is vertical room at scale 1 (rule 5).
    _, motions = draw_sequence([(4000, 3000)] * 1000, seed=2)
    counts = Counter(m.type for m in motions if m.type in PANS)
    vertical = counts[MotionType.PAN_UP] + counts[MotionType.PAN_DOWN]
    horizontal = counts[MotionType.PAN_LEFT] + counts[MotionType.PAN_RIGHT]
    assert vertical > 2 * horizontal


def test_blurred_photos_only_zoom_and_still_alternate() -> None:
    _, motions = draw_sequence([(3000, 4000)] * 50, seed=4)
    assert {m.type for m in motions} <= {MotionType.ZOOM_IN, MotionType.ZOOM_OUT}
    assert all(m.resolved_fit is ResolvedFit.BLUR for m in motions)
    assert all(a.type != b.type for a, b in itertools.pairwise(motions))


def test_mixed_sequences_keep_rule_1_whenever_there_is_a_choice() -> None:
    rng = random.Random(9)
    sizes = [rng.choice([*FILL_SIZES, (3000, 4000), (6000, 2000), (3000, 3000)]) for _ in range(1000)]
    _, motions = draw_sequence(sizes, seed=9)
    options = [option_of(m) for m in motions]
    assert all(a != b for a, b in itertools.pairwise(options))


def test_single_photo_zooms_in() -> None:
    _, motions = draw_sequence([(4000, 3000)])
    assert motions[0].type is MotionType.ZOOM_IN


def test_same_seed_same_motions_different_seed_different() -> None:
    sizes = fill_sizes(200, 1)
    _, a = draw_sequence(sizes, seed=42)
    _, b = draw_sequence(sizes, seed=42)
    _, c = draw_sequence(sizes, seed=43)
    assert a == b
    assert a != c


def test_draw_again_changes_only_that_photo() -> None:
    requests = [request(f"p{i}", *size) for i, size in enumerate(fill_sizes(30, 3))]
    first = draw_motions(requests, 5, Intensity.MEDIUM)
    for target in ("p0", "p7", "p29"):
        again = [
            request(
                r.photo_id,
                r.width,
                r.height,
                draw_count=1 if r.photo_id == target else 0,
                current=first[r.photo_id],
            )
            for r in requests
        ]
        second = draw_motions(again, 5, Intensity.MEDIUM, which=frozenset({target}))
        assert second[target] != first[target]
        assert option_of(second[target]) != option_of(first[target])
        assert second[target].draw_count == 1
        assert {k: v for k, v in second.items() if k != target} == {
            k: v for k, v in first.items() if k != target
        }


def test_draw_again_all_respects_manual_photos() -> None:
    requests = [request(f"p{i}", *size) for i, size in enumerate(fill_sizes(20, 4))]
    first = draw_motions(requests, 1, Intensity.MEDIUM)
    manual = request("p5", *fill_sizes(20, 4)[5], mode=MotionMode.MANUAL, manual_type=MotionType.PAN_LEFT)
    requests[5] = manual
    fixed = draw_motions(requests, 1, Intensity.MEDIUM, which=frozenset({"p5"}))
    assert fixed["p5"].type is MotionType.PAN_LEFT and fixed["p5"].mode is MotionMode.MANUAL
    again = [
        request(
            r.photo_id,
            r.width,
            r.height,
            mode=r.mode,
            manual_type=r.manual_type,
            draw_count=1,
            current=fixed[r.photo_id],
        )
        for r in requests
    ]
    autos = frozenset(r.photo_id for r in requests if r.mode is MotionMode.AUTO)
    second = draw_motions(again, 1, Intensity.MEDIUM, which=autos)
    assert second["p5"].type is MotionType.PAN_LEFT
    changed = sum(1 for pid in autos if option_of(second[pid]) != option_of(first[pid]))
    assert changed == len(autos)


@pytest.mark.parametrize("motion_type", list(MotionType))
def test_manual_types_are_honoured(motion_type: MotionType) -> None:
    req = request("m", 4000, 3000, mode=MotionMode.MANUAL, manual_type=motion_type)
    assert draw_motions([req], 0, Intensity.MEDIUM)["m"].type is motion_type


def test_neighbours_outside_which_are_respected() -> None:
    requests = [request(f"p{i}", 4000, 3000) for i in range(3)]
    first = draw_motions(requests, 8, Intensity.MEDIUM)
    again = [request(r.photo_id, draw_count=1, current=first[r.photo_id]) for r in requests]
    for seed in range(30):
        second = draw_motions(again, seed, Intensity.MEDIUM, which=frozenset({"p1"}))
        middle = option_of(second["p1"])
        assert middle != option_of(first["p0"]) and middle != option_of(first["p2"])


def test_rebuild_keeps_types_when_the_format_changes() -> None:
    sizes = fill_sizes(40, 6)
    requests = [request(f"p{i}", *s) for i, s in enumerate(sizes)]
    first = draw_motions(requests, 2, Intensity.MEDIUM)
    vertical = [
        request(r.photo_id, r.width, r.height, output_format=OutputFormat.VERTICAL, current=first[r.photo_id])
        for r in requests
    ]
    rebuilt = rebuild_motions(vertical, 2, Intensity.MEDIUM)
    # In vertical format these landscape photos become BLUR: only zoom types are possible.
    for r in requests:
        old, new = first[r.photo_id], rebuilt[r.photo_id]
        assert new.resolved_fit is ResolvedFit.BLUR
        if old.type in (MotionType.ZOOM_IN, MotionType.ZOOM_OUT):
            assert new.type is old.type
        else:
            assert new.type in (MotionType.ZOOM_IN, MotionType.ZOOM_OUT)


def test_rebuild_is_identity_when_nothing_changes() -> None:
    requests = [request(f"p{i}", *s) for i, s in enumerate(fill_sizes(40, 8))]
    first = draw_motions(requests, 2, Intensity.MEDIUM)
    same = [request(r.photo_id, r.width, r.height, current=first[r.photo_id]) for r in requests]
    assert rebuild_motions(same, 2, Intensity.MEDIUM) == first


def test_rebuild_after_fit_change_to_fill() -> None:
    req = request("v", 3000, 4000, fit=FitMode.FILL)
    first = draw_motions([req], 1, Intensity.MEDIUM)["v"]
    assert first.resolved_fit is ResolvedFit.FILL
