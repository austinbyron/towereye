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
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    return value if 1 <= value <= 20 else None


class ReaderChain:
    def __init__(self, readers: list[Reader], min_confidence: float = 0.5):
        self.readers = readers
        self.min_confidence = min_confidence

    def read(self, frame: np.ndarray) -> Reading | None:
        best: Reading | None = None
        for reader in self.readers:
            reading = reader.read(frame)
            if reading is None:
                continue
            if reading.confidence >= self.min_confidence:
                return reading
            if best is None or reading.confidence > best.confidence:
                best = reading
        return best
