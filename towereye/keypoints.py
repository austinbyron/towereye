"""Free face matcher: SIFT keypoints on the segmented white lettering.

Matching runs on the numeral constellation (top glyph + adjacent fragments),
not the pearl swirl: Austin owns two near-identical blue d20s, so per-die
swirl fingerprints would break on a die swap, while the lettering comes from
the same mold and transfers. Segmentation keys on paint being color-neutral
(B-R ~ 0) where the die body and its specular glare stay blue-shifted.
Matching is rotation-invariant and verified with a rigid RANSAC fit plus
spread/centrality guards; when this reader answers it is almost certainly
right, everything else falls through the chain.
"""
from pathlib import Path

import cv2
import numpy as np

from .bench import parse_golden_name
from .readers import Reading
from .topface import lettering, topface_crop

SIZE = 256          # working resolution for both templates and queries
# Accept floor swept on 28 labeled real rolls with segmented matching:
# 19/28 answered, zero wrong, stable from floor 6 all the way down to 4.
MIN_INLIERS = 6
# Margin swept on 28 labeled rolls: 1.5 answers 21/28 at 0 wrong. The spread
# and centrality guards now zero junk scores, so 2.0 was over-refusing (a
# correct 17 at 11 inliers was blocked by a runner-up at 6).
MARGIN = 1.5
RATIO = 0.75        # Lowe's ratio test for candidate matches
MIN_SPREAD = 0.15   # inliers must span this fraction of the image both ways
CENTER_TOL = 0.30   # inlier centroid must sit this close to the image center


def _spread_ok(points: np.ndarray) -> bool:
    """Reject collinear/clustered inlier sets: a straight shadow edge can
    'match' another straight edge with a consistent affine fit."""
    spread = points.max(axis=0) - points.min(axis=0)
    return bool(min(spread) >= MIN_SPREAD * SIZE)


def _centered_ok(points: np.ndarray) -> bool:
    """Reject edge-clustered inlier sets: crops include fragments of the three
    adjacent faces, and two neighboring faces' crops share real surface, so an
    edge-heavy match means the wrong (adjacent) face, not the top face."""
    cx, cy = points.mean(axis=0)
    return bool(np.hypot(cx - SIZE / 2, cy - SIZE / 2) <= CENTER_TOL * SIZE)


class KeypointReader:
    name = "keypoints"

    def __init__(self, template_dir: str | Path = "templates"):
        self._sift = cv2.SIFT_create()
        self._bf = cv2.BFMatcher()
        self.templates: list[tuple[int, list, np.ndarray]] = []
        for path in sorted(Path(template_dir).glob("*.png")):
            value = parse_golden_name(path)
            img = cv2.imread(str(path))
            if value is None or img is None:
                continue
            kp, des = self._features(img)
            if des is not None and len(kp) >= 4:
                self.templates.append((value, kp, des))

    def _features(self, img: np.ndarray):
        img = cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_CUBIC)
        return self._sift.detectAndCompute(lettering(img), None)

    def _inliers(self, kp1, des1, kp2, des2) -> int:
        matches = self._bf.knnMatch(des1, des2, k=2)
        good = [m for m, n in matches if m.distance < RATIO * n.distance]
        if len(good) < 4:
            return 0
        src = np.float32([kp1[m.queryIdx].pt for m in good])
        dst = np.float32([kp2[m.trainIdx].pt for m in good])
        _, mask = cv2.estimateAffinePartial2D(src, dst, ransacReprojThreshold=4.0)
        if mask is None:
            return 0
        keep = mask.ravel().astype(bool)
        query_inliers, tmpl_inliers = src[keep], dst[keep]
        if len(query_inliers) < 4 or not _spread_ok(query_inliers):
            return 0
        if not (_centered_ok(query_inliers) and _centered_ok(tmpl_inliers)):
            return 0
        return int(mask.sum())

    def read(self, frame: np.ndarray) -> Reading | None:
        if not self.templates:
            return None
        kp, des = self._features(frame)
        if des is None or len(kp) < 4:
            return None
        best: dict[int, int] = {}
        for value, tkp, tdes in self.templates:
            score = self._inliers(kp, des, tkp, tdes)
            best[value] = max(best.get(value, 0), score)
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        top_value, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        if top_score >= MIN_INLIERS and top_score >= MARGIN * max(runner_up, 1):
            return Reading(value=top_value, confidence=0.95, reader=self.name)
        return None


def save_template(frame: np.ndarray, value: int, out_dir: str | Path) -> Path | None:
    """Save the frame's top-face crop as the next '<value>_<n>.png' template."""
    crop = topface_crop(frame)
    if crop is None:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    while (path := out_dir / f"{value}_{n:03d}.png").exists():
        n += 1
    cv2.imwrite(str(path), crop)
    return path
