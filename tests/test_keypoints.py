import cv2
import numpy as np

from towereye.keypoints import KeypointReader, save_template


def _textured(seed):
    """A pearlescent-swirl stand-in: blurred noise is feature-rich like the die."""
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (256, 256), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (5, 5), 0)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def _rotated(img, deg):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, m, (w, h))


def test_matches_rotated_face_against_template(tmp_path):
    cv2.imwrite(str(tmp_path / "7_000.png"), _textured(1))
    cv2.imwrite(str(tmp_path / "9_000.png"), _textured(2))
    reader = KeypointReader(template_dir=tmp_path)
    reading = reader.read(_rotated(_textured(1), 30))
    assert reading is not None
    assert reading.value == 7
    assert reading.reader == "keypoints"
    assert reading.confidence >= 0.5  # short-circuits the chain when it fires


def test_unknown_face_returns_none(tmp_path):
    cv2.imwrite(str(tmp_path / "7_000.png"), _textured(1))
    reader = KeypointReader(template_dir=tmp_path)
    assert reader.read(_textured(5)) is None


def test_no_templates_reads_none(tmp_path):
    reader = KeypointReader(template_dir=tmp_path)
    assert reader.templates == []
    assert reader.read(_textured(1)) is None


def test_save_template_crops_and_numbers_files(tmp_path):
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[60:140, 60:140] = (255, 120, 100)
    p1 = save_template(frame, 17, tmp_path)
    p2 = save_template(frame, 17, tmp_path)
    assert p1.name == "17_000.png" and p2.name == "17_001.png"
    saved = cv2.imread(str(p1))
    assert saved.shape[0] < 80  # the top-face crop, not the full frame


def test_save_template_without_die_returns_none(tmp_path):
    assert save_template(np.zeros((200, 200, 3), dtype=np.uint8), 17, tmp_path) is None
