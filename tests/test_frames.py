import numpy as np

from towereye.frames import CameraSource


class FakeCap:
    """Scripted VideoCapture: each entry is a frame, or None for a failed read."""

    def __init__(self, script, opened=True):
        self.script = list(script)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.script:
            return False, None
        item = self.script.pop(0)
        return (item is not None), item

    def release(self):
        self.released = True


def test_camera_source_reconnects_after_a_dropped_read(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("towereye.frames.time.monotonic", lambda: clock[0])
    def sleep(s):
        clock[0] += s
    f = np.zeros((2, 2, 3), np.uint8)
    caps = [FakeCap([f, None]), FakeCap([], opened=False), FakeCap([f, f, f])]
    opened = []
    def opener(spec):
        cap = caps.pop(0) if caps else FakeCap([], opened=False)  # after the script: camera gone for good
        opened.append(cap)
        return cap
    logs = []
    src = CameraSource(1, reconnect_seconds=5, opener=opener, sleep=sleep, log=logs.append)
    got = list(src.frames())
    assert len(got) == 1 + 2   # first frame, then the reconnect's probe consumes one, two remain
    assert all(c.released for c in opened[:2])
    assert any("retrying" in m for m in logs) and any("is back" in m for m in logs)


def test_camera_source_gives_up_after_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("towereye.frames.time.monotonic", lambda: clock[0])
    def sleep(s):
        clock[0] += s
    def opener(spec):
        return FakeCap([], opened=False) if clock[0] > 0 else FakeCap([None])
    logs = []
    src = CameraSource(1, reconnect_seconds=3, opener=opener, sleep=sleep, log=logs.append)
    assert list(src.frames()) == []
    assert any("did not come back" in m for m in logs)
