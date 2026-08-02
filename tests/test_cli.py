import os

import numpy as np

from towereye.cli import _load_dotenv, _zoom_frames, run_watch
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


def _throw_frames(color=(255, 120, 100)):
    def square(x):
        f = np.zeros((48, 64, 3), dtype=np.uint8)
        f[10:30, x : x + 20] = color
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


def test_run_watch_skips_settles_without_a_die():
    lines = []
    logger = ListLogger()
    # a gray blob settles (hand / empty-tray motion), then a blue die settles
    frames = _throw_frames(color=(128, 128, 128)) + _throw_frames()
    run_watch(
        frames=iter(frames),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        report=lines.append,
    )
    assert len(logger.entries) == 1  # gray settle neither reported nor logged
    assert sum("You rolled 7" in line for line in lines) == 1


def test_load_dotenv_fills_missing_vars_without_clobbering(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TOWEREYE_TEST_KEY=abc\n# comment\n\nTOWEREYE_TEST_SET=new\nTOWEREYE_TEST_EMPTY=\n")
    monkeypatch.setenv("TOWEREYE_TEST_SET", "old")
    try:
        _load_dotenv(env)
        assert os.environ["TOWEREYE_TEST_KEY"] == "abc"
        assert os.environ["TOWEREYE_TEST_SET"] == "old"  # real env wins
        assert "TOWEREYE_TEST_EMPTY" not in os.environ  # unfilled seed line ignored
    finally:
        os.environ.pop("TOWEREYE_TEST_KEY", None)


def test_load_dotenv_missing_file_is_noop(tmp_path):
    _load_dotenv(tmp_path / ".env")


class RecordingReader(FixedReader):
    def __init__(self, value):
        super().__init__(value)
        self.frames = []

    def read(self, frame):
        self.frames.append(frame)
        return super().read(frame)


def _die_square(x, sharp=False):
    """A die-sized (70px, r~40) blob so die_blob() sees it, in a 160x240 frame."""
    f = np.zeros((160, 240, 3), dtype=np.uint8)
    f[45:115, x : x + 70] = (255, 120, 100)
    if sharp:
        f[72:88, x + 15 : x + 55] = (255, 255, 255)  # crisp numeral detail
    return f


def test_run_watch_reads_the_sharpest_post_settle_frame():
    import cv2

    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    blurred = [cv2.GaussianBlur(f, (21, 21), 8) for f in throw]
    sharp_tail = [_die_square(60, sharp=True)] * 8  # focus catches up, die unmoved
    reader = RecordingReader(7)
    run_watch(
        frames=iter(blurred + sharp_tail),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=reader,
        logger=ListLogger(),
        report=lambda _: None,
    )
    assert reader.frames  # a roll was read
    from towereye.topface import sharpness

    assert sharpness(reader.frames[0]) > sharpness(blurred[-1])


def test_run_watch_ignores_post_settle_frames_where_die_moved():
    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    # after settling at x=60, the die is picked up: sharper frames, wrong place
    grabbed = [_die_square(160, sharp=True)] * 15
    reader = RecordingReader(7)
    run_watch(
        frames=iter(throw + grabbed),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=reader,
        logger=ListLogger(),
        report=lambda _: None,
    )
    assert reader.frames
    from towereye.topface import die_blob

    cx, _, _ = die_blob(reader.frames[0])
    assert abs(cx - 95) < 8  # the settled die (center x=95), not the moved one (x=195)


def test_zoom_frames_center_crops():
    f = np.zeros((90, 120, 3), dtype=np.uint8)
    f[30:60, 40:80] = (255, 120, 100)  # central third survives any zoom <= 3x
    (out,) = _zoom_frames(iter([f]), 1.5)
    assert out.shape == (60, 80, 3)
    assert (out[15:45, 20:60] == (255, 120, 100)).all()


def test_zoom_frames_at_1x_is_identity():
    f = np.arange(90 * 120 * 3, dtype=np.uint8).reshape(90, 120, 3)
    (out,) = _zoom_frames(iter([f]), 1.0)
    assert out is f
