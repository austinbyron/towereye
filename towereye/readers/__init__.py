"""Reader protocol, value parsing, and the cheapest-first reader chain."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Reading:
    value: int
    confidence: float
    reader: str


class Reader(Protocol):
    name: str

    def read(self, frame: np.ndarray) -> Reading | None: ...


def parse_die_value(text: str) -> int | None:
    """Parse OCR/LLM output into a die value 1-20, tolerating 6./9_ marks."""
    cleaned = text.strip().strip("._,")
    if not cleaned.isdigit() or cleaned.startswith("0"):
        return None  # leading zero = upside-down read (01 is a flipped 10)
    value = int(cleaned)
    return value if 1 <= value <= 20 else None


# Crop scales tried in order when the default crop yields no confident read:
# a touch wider (recovers digits clipped by an off-center window) and a touch
# tighter (sheds adjacent-face fragments). 0.75 stays first: it is the
# validated default and both alternates lose answers when used alone.
CROP_SCALES = (0.75, 0.85, 0.68)


class ReaderChain:
    def __init__(self, readers: list[Reader], min_confidence: float = 0.5,
                 crop_scales: tuple[float, ...] = CROP_SCALES):
        self.readers = readers
        self.min_confidence = min_confidence
        self.crop_scales = crop_scales

    def _read_crop(self, crop: np.ndarray) -> Reading | None:
        for reader in self.readers:
            reading = reader.read(crop)
            if reading is not None and reading.confidence >= self.min_confidence:
                return reading
        return None

    def read(self, frame: np.ndarray) -> Reading | None:
        """Confident reading or None; every reader gets every crop variant
        before we give up on a frame. Low-confidence guesses are never
        returned: a wrong number in chat is worse than asking for a reroll."""
        from ..topface import topface_crop

        cropped = False
        for scale in self.crop_scales:
            crop = topface_crop(frame, scale)
            if crop is None:
                continue
            cropped = True
            reading = self._read_crop(crop)
            if reading is not None:
                return reading
        if cropped:
            return None
        return self._read_crop(frame)  # no die blob: let readers see everything
