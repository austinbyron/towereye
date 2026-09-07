import cv2
import numpy as np

from towereye.keypoints import KeypointReader, save_template


def _textured(seed):
    """A die-face stand-in: white lettering-like strokes on a blue body,
    so the lettering segmentation keeps them."""
    rng = np.random.default_rng(seed)
    img = np.full((256, 256, 3), (140, 40, 30), dtype=np.uint8)  # blue body
    white = (250, 245, 240)
    for gx in range(3):
        for gy in range(3):
            cx, cy = 64 + gx * 64, 64 + gy * 64  # separate glyph-sized marks
            dx, dy, r = rng.integers(-18, 18, 2).tolist() + [int(rng.integers(8, 16))]
            if rng.integers(2):
                cv2.circle(img, (cx + dx, cy + dy), r, white, 5)
            else:
                cv2.line(img, (cx - r + dx, cy + dy), (cx + r + dx, cy - r + dy), white, 6)
    return img


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


def test_spread_guard_rejects_collinear_inliers():
    from towereye.keypoints import _spread_ok

    line = np.float32([[10, 128], [80, 128], [150, 129], [220, 128]])
    scattered = np.float32([[40, 40], [200, 60], [60, 210], [190, 200]])
    assert not _spread_ok(line)
    assert _spread_ok(scattered)


def test_center_guard_rejects_edge_clustered_inliers():
    from towereye.keypoints import _centered_ok

    corner = np.float32([[10, 10], [60, 20], [20, 60], [50, 50]])
    central = np.float32([[100, 100], [160, 110], [110, 160], [150, 150]])
    assert not _centered_ok(corner)
    assert _centered_ok(central)


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


def test_shape_agreement_rewards_matching_glyphs_and_punishes_extra_strokes():
    import cv2
    import numpy as np
    from towereye.keypoints import SIZE, KeypointReader

    def glyph_mask(extra_stroke):
        m = np.zeros((SIZE, SIZE), np.uint8)
        cv2.ellipse(m, (SIZE // 2, SIZE // 2), (40, 55), 0, 0, 360, 1, 12)  # a "0"
        if extra_stroke:
            cv2.line(m, (SIZE // 2 - 70, SIZE // 2 - 55), (SIZE // 2 - 70, SIZE // 2 + 55), 1, 12)  # "10"
        return m

    identity = np.float32([[1, 0, 0], [0, 1, 0]])
    same = KeypointReader._shape_agreement(glyph_mask(False), glyph_mask(False), identity)
    extra = KeypointReader._shape_agreement(glyph_mask(False), glyph_mask(True), identity)
    assert same > 0.99
    assert extra < same * 0.8
