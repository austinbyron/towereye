import numpy as np

from towereye.presence import die_present

BLUE = (255, 120, 100)  # BGR; hue ~112, saturated and bright enough to pass the band


def _frame(h=100, w=100):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_blue_blob_in_center_is_present():
    f = _frame()
    f[40:60, 40:60] = BLUE
    assert die_present(f)


def test_empty_frame_is_absent():
    assert not die_present(_frame())


def test_gray_blob_is_absent():
    f = _frame()
    f[40:60, 40:60] = (128, 128, 128)
    assert not die_present(f)


def test_tiny_blue_speck_is_absent():
    f = _frame()
    f[50, 50] = BLUE
    assert not die_present(f)


def test_blue_blob_outside_center_crop_is_absent():
    f = _frame()
    f[0:10, 0:10] = BLUE
    assert not die_present(f)


def test_wider_crop_sees_edge_blob():
    # a pre-zoomed frame passes a widened crop so tray-edge dice aren't lost
    f = _frame()
    f[6:16, 40:60] = BLUE  # near top edge: outside default crop, inside 0.9
    assert not die_present(f)
    assert die_present(f, center_crop=0.9)
