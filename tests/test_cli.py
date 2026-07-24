import numpy as np

from towereye.cli import run_watch
from towereye.readers import Reading
from towereye.settle import SettleDetector


class FixedReader:
    name = "fixed"

    def __init__(self, value):
        self._value = value

    def read(self, frame):
        return Reading(value=self._value, confidence=1.0, reader=self.name)


class ListLogger:
    def __init__(self):
        self.entries = []

    def log(self, frame, reading, context=None):
        self.entries.append(reading)
        return "test-id"


def _throw_frames():
    def square(x):
        f = np.zeros((48, 64, 3), dtype=np.uint8)
        f[10:30, x : x + 20] = 255
        return f

    return [square(x) for x in range(0, 30, 6)] + [square(24)] * 10


def test_run_watch_reports_and_logs_settled_roll():
    lines = []
    logger = ListLogger()
    run_watch(
        frames=iter(_throw_frames()),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        report=lines.append,
    )
    assert any("You rolled 7" in line for line in lines)
    assert len(logger.entries) == 1
    assert logger.entries[0].value == 7
