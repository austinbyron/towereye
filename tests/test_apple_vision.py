import sys

import numpy as np
import pytest

darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="Vision framework is macOS-only")


def _digit_frame(text: str, size=200):
    """White frame with large black digits, rendered via PIL."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except OSError:
        font = ImageFont.load_default(size=120)
    draw.text((size // 2, size // 2), text, fill="black", font=font, anchor="mm")
    rgb = np.array(img)
    return rgb[:, :, ::-1].copy()  # RGB -> BGR


@darwin_only
def test_reads_two_digit_number():
    from towereye.readers.apple_vision import AppleVisionReader

    reading = AppleVisionReader().read(_digit_frame("17"))
    assert reading is not None
    assert reading.value == 17
    assert reading.reader == "apple_vision"
    assert 0.0 < reading.confidence <= 1.0


@darwin_only
def test_blank_frame_returns_none():
    from towereye.readers.apple_vision import AppleVisionReader

    blank = np.full((200, 200, 3), 255, dtype=np.uint8)
    assert AppleVisionReader().read(blank) is None


@darwin_only
def test_reads_rotated_digits():
    from towereye.readers.apple_vision import AppleVisionReader

    upside_down = np.rot90(_digit_frame("17"), 2).copy()
    reading = AppleVisionReader().read(upside_down)
    assert reading is not None
    assert reading.value == 17


def test_select_prefers_center_over_confidence():
    from towereye.readers.apple_vision import _select

    # (value, confidence, distance-from-center): side face is crisper but off-center
    reading = _select([(17, 1.0, 0.28), (10, 0.6, 0.05)], "apple_vision")
    assert reading.value == 10
    assert reading.confidence == 0.6


def test_select_demotes_conflicting_values_near_center():
    from towereye.readers.apple_vision import _select

    # rotation sweep read the same numeral as 17 and 11 at similar centrality:
    # Vision can't be trusted, so confidence drops below the chain gate
    reading = _select([(11, 1.0, 0.16), (17, 1.0, 0.17)], "apple_vision")
    assert reading.confidence < 0.5


def test_select_ignores_distant_rival_values():
    from towereye.readers.apple_vision import _select

    # a side numeral surviving at the crop edge is not a conflict
    reading = _select([(10, 1.0, 0.05), (17, 1.0, 0.28)], "apple_vision")
    assert reading.value == 10
    assert reading.confidence == 1.0


def test_select_rejects_far_and_weak_candidates():
    from towereye.readers.apple_vision import _select

    assert _select([(17, 1.0, 0.45)], "apple_vision") is None  # too far off-center
    assert _select([(17, 0.1, 0.05)], "apple_vision") is None  # too low confidence
    assert _select([], "apple_vision") is None
