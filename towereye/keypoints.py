"""Free per-die face matcher: SIFT keypoints against calibrated face templates.

The die's pearlescent swirl is baked into the plastic, so every face is a fixed
visual fingerprint. Matching is rotation-invariant and verified with a rigid
RANSAC fit, which is exactly the physics of a settled die under a fixed camera.
Conservative accept thresholds: when this reader answers it is almost certainly
right; everything else falls through the chain.
"""
from pathlib import Path

import cv2
import numpy as np

from .bench import parse_golden_name
from .readers import Reading
from .topface import topface_crop

SIZE = 256          # working resolution for both templates and queries
MIN_INLIERS = 15    # accept floor: geometric inliers against the best template
MARGIN = 2.0        # best value must beat the runner-up value by this factor
RATIO = 0.75        # Lowe's ratio test for candidate matches


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
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return self._sift.detectAndCompute(gray, None)

    def _inliers(self, kp1, des1, kp2, des2) -> int:
        matches = self._bf.knnMatch(des1, des2, k=2)
        good = [m for m, n in matches if m.distance < RATIO * n.distance]
        if len(good) < 4:
            return 0
        src = np.float32([kp1[m.queryIdx].pt for m in good])
        dst = np.float32([kp2[m.trainIdx].pt for m in good])
        _, mask = cv2.estimateAffinePartial2D(src, dst, ransacReprojThreshold=4.0)
        return int(mask.sum()) if mask is not None else 0

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
