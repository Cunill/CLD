"""B3 · Fit decision (§1.6)."""

from __future__ import annotations

import pytest

from passimaker.model.types import FitMode, OutputFormat, ResolvedFit
from passimaker.motion import FILL_RATIO_RANGE, base_window, output_aspect, resolve_fit

H, V = OutputFormat.HORIZONTAL, OutputFormat.VERTICAL
H32, H43, V23, V34 = (
    OutputFormat.HORIZONTAL_3_2,
    OutputFormat.HORIZONTAL_4_3,
    OutputFormat.VERTICAL_2_3,
    OutputFormat.VERTICAL_3_4,
)


@pytest.mark.parametrize(
    ("width", "height", "output_format", "expected"),
    [
        (4000, 3000, H, ResolvedFit.FILL),  # 4:3
        (3000, 2000, H, ResolvedFit.FILL),  # 3:2
        (1920, 1080, H, ResolvedFit.FILL),  # 16:9
        (1920, 1200, H, ResolvedFit.FILL),  # 16:10
        (5000, 4000, H, ResolvedFit.FILL),  # 5:4 (ratio 0.703)
        (3000, 3000, H, ResolvedFit.BLUR),  # 1:1
        (3000, 4000, H, ResolvedFit.BLUR),  # vertical 3:4
        (1080, 1920, H, ResolvedFit.BLUR),  # vertical 9:16
        (6000, 2000, H, ResolvedFit.BLUR),  # panorama 3:1
        (3000, 4000, V, ResolvedFit.FILL),  # 3:4 in vertical video
        (2000, 3000, V, ResolvedFit.FILL),  # 2:3
        (1080, 1920, V, ResolvedFit.FILL),  # 9:16
        (3000, 3000, V, ResolvedFit.BLUR),  # 1:1
        (4000, 3000, V, ResolvedFit.BLUR),  # 4:3 in vertical video
        (1920, 1080, V, ResolvedFit.BLUR),  # 16:9 in vertical video
        # M10: the same rule with the other proportions.
        (4000, 3000, H43, ResolvedFit.FILL),  # 4:3 in 4:3, exact
        (3000, 3000, H43, ResolvedFit.FILL),  # 1:1 in 4:3 (ratio 0.75)
        (1920, 1080, H43, ResolvedFit.FILL),  # 16:9 in 4:3 (ratio 1.33)
        (3000, 4000, H43, ResolvedFit.BLUR),  # vertical 3:4
        (6000, 2000, H43, ResolvedFit.BLUR),  # panorama 3:1
        (3000, 2000, H32, ResolvedFit.FILL),  # 3:2 in 3:2, exact
        (3000, 3000, H32, ResolvedFit.BLUR),  # 1:1 in 3:2 (ratio 0.67)
        (2000, 3000, V23, ResolvedFit.FILL),  # 2:3 in 2:3, exact
        (3000, 3000, V23, ResolvedFit.BLUR),  # 1:1 in 2:3 (ratio 1.5)
        (3000, 4000, V34, ResolvedFit.FILL),  # 3:4 in 3:4, exact
        (3000, 3000, V34, ResolvedFit.FILL),  # 1:1 in 3:4 (ratio 1.33)
        (4000, 3000, V34, ResolvedFit.BLUR),  # 4:3 in 3:4
    ],
)
def test_automatic_fit(width: int, height: int, output_format: OutputFormat, expected: ResolvedFit) -> None:
    assert resolve_fit(width, height, output_format, FitMode.AUTO).fit is expected


def test_range_limits_are_inclusive() -> None:
    low, high = FILL_RATIO_RANGE
    video = output_aspect(H)
    for ratio in (low, high):
        width = 10_000
        height = round(width / (ratio * video))
        actual = (width / height) / video
        fit = resolve_fit(width, height, H, FitMode.AUTO).fit
        assert fit is (ResolvedFit.FILL if low <= actual <= high else ResolvedFit.BLUR)
    assert resolve_fit(10_000, round(10_000 / (0.69 * video)), H, FitMode.AUTO).fit is ResolvedFit.BLUR
    assert resolve_fit(10_000, round(10_000 / (1.44 * video)), H, FitMode.AUTO).fit is ResolvedFit.BLUR


@pytest.mark.parametrize(
    ("preference", "expected"),
    [(FitMode.FILL, ResolvedFit.FILL), (FitMode.BLUR, ResolvedFit.BLUR), (FitMode.BLACK, ResolvedFit.BLACK)],
)
def test_user_preference_overrides(preference: FitMode, expected: ResolvedFit) -> None:
    assert resolve_fit(3000, 4000, H, preference).fit is expected
    assert resolve_fit(4000, 3000, H, preference).fit is expected


@pytest.mark.parametrize("output_format", list(OutputFormat))
@pytest.mark.parametrize(("width", "height"), [(3000, 4000), (6000, 2000), (3000, 3000), (4000, 3000)])
def test_composed_canvas_has_video_aspect_and_contains_photo(
    output_format: OutputFormat, width: int, height: int
) -> None:
    decision = resolve_fit(width, height, output_format, FitMode.BLUR)
    assert decision.canvas_width >= width and decision.canvas_height >= height
    assert decision.canvas_width / decision.canvas_height == pytest.approx(
        output_aspect(output_format), rel=1e-3
    )
    assert min(decision.canvas_width - width, decision.canvas_height - height) == 0


def test_fill_canvas_is_the_photo() -> None:
    decision = resolve_fit(4000, 3000, H, FitMode.AUTO)
    assert (decision.canvas_width, decision.canvas_height) == (4000, 3000)


def test_base_window() -> None:
    assert base_window(4000, 3000, H) == pytest.approx((1.0, 0.75))  # 4:3 in 16:9: full width
    assert base_window(6000, 2000, H) == pytest.approx((16 / 9 / 3, 1.0))
    assert base_window(1920, 1080, H) == pytest.approx((1.0, 1.0))
    assert base_window(3000, 4000, V) == pytest.approx((0.5625 / 0.75, 1.0))  # 3:4 in 9:16: full height


def test_invalid_size() -> None:
    with pytest.raises(ValueError):
        resolve_fit(0, 100, H, FitMode.AUTO)
