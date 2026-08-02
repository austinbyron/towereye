import numpy as np

from towereye.presence import die_present

BLUE = (255, 120, 100)  # BGR; hue ~112, saturated and bright enough to pass the band


def _frame(h=300, w=300):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_blue_die_in_center_is_present():
    f = _frame()
    f[110:190, 110:190] = BLUE  # die-sized blob (r ~45)
    assert die_present(f)


def test_empty_frame_is_absent():
    assert not die_present(_frame())


def test_gray_blob_is_absent():
    f = _frame()
    f[110:190, 110:190] = (128, 128, 128)
    assert not die_present(f)


def test_small_speck_is_absent():
    f = _frame()
    f[145:165, 145:165] = BLUE  # r ~11, well under a die
    assert not die_present(f)


def test_full_frame_gate_sees_edge_die():
    f = _frame()
    f[5:85, 110:190] = BLUE  # die parked at the tray edge
    assert not die_present(f)                    # default center crop misses it
    assert die_present(f, center_crop=1.0)       # watch's full-frame gate does not
