import cv2
import numpy as np

from towereye.calibrate import Calibrator, LatestFrame


def _die_frame():
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    frame[110:190, 110:190] = (255, 120, 100)  # blue blob = a die
    return frame


class FakeKeypoints:
    def __init__(self):
        self.added = []

    def add_template(self, img, value, die):
        self.added.append((img.shape, value, die))


def test_latest_frame_tees_and_remembers():
    latest = LatestFrame()
    frames = [np.zeros((2, 2, 3), np.uint8), np.ones((2, 2, 3), np.uint8)]
    out = list(latest.tee(iter(frames)))
    assert len(out) == 2
    assert latest.frame is frames[1]


def test_start_requires_a_specific_die(tmp_path):
    cal = Calibrator(tmp_path)
    assert cal.start("auto")["type"] == "calibrate_error"
    assert cal.start("d7")["type"] == "calibrate_error"
    assert not cal.active
    state = cal.start("D8")
    assert state == {"type": "calibrating", "die": "d8", "faces": 8,
                     "counts": {str(v): 0 for v in range(1, 9)}}
    assert cal.active
    assert cal.stop() == {"type": "calibrating", "die": None}


def test_save_writes_pool_file_grows_reader_and_counts(tmp_path):
    kp = FakeKeypoints()
    frame = _die_frame()
    cal = Calibrator(tmp_path, keypoints=kp, latest=lambda: frame)
    assert cal.save(3)["type"] == "calibrate_error"  # not started
    cal.start("d8")
    reply = cal.save("3")
    assert reply["type"] == "template_saved"
    assert reply["die"] == "d8" and reply["value"] == 3
    assert (tmp_path / "d8" / "3_000.png").exists()
    assert reply["counts"]["3"] == 1
    assert kp.added and kp.added[0][1:] == (3, "d8")
    cal.save(3)
    assert cal.counts("d8")["3"] == 2
    assert cal.save(9)["type"] == "calibrate_error"  # d8 has no 9
    assert cal.save("x")["type"] == "calibrate_error"


def test_save_without_frame_or_die_reports_why(tmp_path):
    cal = Calibrator(tmp_path, latest=lambda: None)
    cal.start("d20")
    assert "no camera frame" in cal.save(1)["reason"]
    blank = np.zeros((300, 300, 3), dtype=np.uint8)
    cal = Calibrator(tmp_path, latest=lambda: blank)
    cal.start("d20")
    assert "no die found" in cal.save(1)["reason"]


def test_handle_dispatches_requests(tmp_path):
    frame = _die_frame()
    cal = Calibrator(tmp_path, latest=lambda: frame)
    pools = cal.handle({"type": "templates"})
    assert pools["type"] == "templates" and set(pools["pools"]) == {"d4", "d6", "d8", "d10", "d12", "d20"}
    assert cal.handle({"type": "calibrate_start", "die": "d6"})["faces"] == 6
    assert cal.handle({"type": "calibrate_save", "value": 2})["type"] == "template_saved"
    assert cal.handle({"type": "calibrate_stop"})["die"] is None
    assert cal.handle({"type": "arm"}) is None
