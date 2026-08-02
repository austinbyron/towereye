import numpy as np

from towereye.topface import topface_crop

BLUE = (255, 120, 100)


def _frame(h=200, w=200):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_crop_centers_on_offset_die():
    f = _frame()
    f[20:90, 100:170] = BLUE  # die-sized blob away from frame center
    crop = topface_crop(f)
    assert crop is not None
    assert crop.shape[0] < 70 and crop.shape[1] < 70  # tighter than the blob
    # crop is all-die: every pixel came from the blue region
    assert (crop == BLUE).all()


def test_no_die_returns_none():
    assert topface_crop(_frame()) is None


def test_tiny_speck_returns_none():
    f = _frame()
    f[100:103, 100:103] = BLUE
    assert topface_crop(f) is None


def test_sharpness_prefers_crisp_frame():
    import cv2

    from towereye.topface import sharpness

    f = _frame()
    f[60:140, 60:140] = BLUE
    f[95:105, 80:120] = (255, 255, 255)  # numeral-ish detail
    blurred = cv2.GaussianBlur(f, (21, 21), 8)
    assert sharpness(f) > sharpness(blurred)
