import cv2
import numpy as np

from towereye.bench import parse_golden_name, run_bench
from towereye.readers import Reading


class FixedReader:
    def __init__(self, value):
        self._value = value

    def read(self, frame):
        if self._value is None:
            return None
        return Reading(value=self._value, confidence=1.0, reader="fixed")


def test_parse_golden_name():
    from pathlib import Path

    assert parse_golden_name(Path("17_003.png")) == 17
    assert parse_golden_name(Path("6_a.png")) == 6
    assert parse_golden_name(Path("notes.png")) is None


def test_run_bench_scores_against_labels(tmp_path):
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "17_001.png"), frame)
    cv2.imwrite(str(tmp_path / "3_001.png"), frame)
    correct, total, mismatches = run_bench(tmp_path, FixedReader(17))
    assert (correct, total) == (1, 2)
    assert len(mismatches) == 1 and "3_001" in mismatches[0]
