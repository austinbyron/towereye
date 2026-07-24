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
