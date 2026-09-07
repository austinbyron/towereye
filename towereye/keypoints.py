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
# Accept floor: with shape verification as the safety net, 4 answers 51/61
# labeled frames at zero wrong (2026-09-06 sweep); without it, 4 produced
# four wrongs where the true face's template scored zero and junk won.
MIN_INLIERS = 4
# Margin swept on 28 labeled rolls: 1.5 answers 21/28 at 0 wrong. The spread
# and centrality guards now zero junk scores, so 2.0 was over-refusing (a
# correct 17 at 11 inliers was blocked by a runner-up at 6).
MARGIN = 1.5
# Shape verification: the top candidate's warped glyph mask must overlap the
# query's this well, and beat the runner-up's overlap by this factor when the
# inlier margin alone can't decide.
IOU_MIN = 0.35
IOU_MARGIN = 1.3
DISC_FRAC = 0.45
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


_yy, _xx = np.mgrid[0:SIZE, 0:SIZE]
_DISC = np.hypot(_xx - SIZE / 2, _yy - SIZE / 2) <= DISC_FRAC * SIZE


class KeypointReader:
    name = "keypoints"

    def __init__(self, template_dir: str | Path = "templates"):
        self._sift = cv2.SIFT_create()
        self._bf = cv2.BFMatcher()
        self.templates: list[tuple[int, list, np.ndarray, np.ndarray]] = []
        for path in sorted(Path(template_dir).glob("*.png")):
            value = parse_golden_name(path)
            img = cv2.imread(str(path))
            if value is None or img is None:
                continue
            kp, des, mask = self._features(img)
            if des is not None and len(kp) >= 4:
                self.templates.append((value, kp, des, mask))

    def _features(self, img: np.ndarray):
        img = cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_CUBIC)
        glyphs = lettering(img)
        kp, des = self._sift.detectAndCompute(glyphs, None)
        return kp, des, (glyphs > 0).astype(np.uint8)

    def _match(self, kp1, des1, kp2, des2) -> tuple[set[int], np.ndarray | None]:
        """Query keypoint indices that survive ratio test, RANSAC, and the
        spread/centrality guards, plus the query->template affine; empty when
        the match is junk."""
        matches = self._bf.knnMatch(des1, des2, k=2)
        good = [m for m, n in matches if m.distance < RATIO * n.distance]
        if len(good) < 4:
            return set(), None
        src = np.float32([kp1[m.queryIdx].pt for m in good])
        dst = np.float32([kp2[m.trainIdx].pt for m in good])
        affine, mask = cv2.estimateAffinePartial2D(src, dst, ransacReprojThreshold=4.0)
        if mask is None or affine is None:
            return set(), None
        keep = mask.ravel().astype(bool)
        query_inliers, tmpl_inliers = src[keep], dst[keep]
        if len(query_inliers) < 4 or not _spread_ok(query_inliers):
            return set(), None
        if not (_centered_ok(query_inliers) and _centered_ok(tmpl_inliers)):
            return set(), None
        return {m.queryIdx for m, k in zip(good, keep) if k}, affine

    def _inlier_set(self, kp1, des1, kp2, des2) -> set[int]:
        return self._match(kp1, des1, kp2, des2)[0]

    def _inliers(self, kp1, des1, kp2, des2) -> int:
        return len(self._inlier_set(kp1, des1, kp2, des2))

    @staticmethod
    def _shape_agreement(query_mask: np.ndarray, tmpl_mask: np.ndarray, affine: np.ndarray) -> float:
        """IoU of the glyph masks after warping the template onto the query,
        judged in the central disc so adjacent-face fragments don't vote.
        Keypoints can't tell a 9 from the rotated 6 inside a 16; the 16's
        extra stroke landing on bare body can."""
        inv = cv2.invertAffineTransform(affine)
        warped = cv2.warpAffine(tmpl_mask, inv, (SIZE, SIZE), flags=cv2.INTER_NEAREST)
        q, t = query_mask.astype(bool) & _DISC, warped.astype(bool) & _DISC
        union = (q | t).sum()
        return float((q & t).sum() / union) if union else 0.0

    def read(self, frame: np.ndarray) -> Reading | None:
        if not self.templates:
            return None
        kp, des, qmask = self._features(frame)
        if des is None or len(kp) < 4:
            return None
        best: dict[int, tuple[set[int], float]] = {}
        for value, tkp, tdes, tmask in self.templates:
            found, affine = self._match(kp, des, tkp, tdes)
            if len(found) > len(best.setdefault(value, (set(), 0.0))[0]):
                best[value] = (found, self._shape_agreement(qmask, tmask, affine))
        ranked = sorted(best.items(), key=lambda kv: -len(kv[1][0]))
        top_value, (top, top_iou) = ranked[0]
        runner_up, runner_iou = ranked[1][1] if len(ranked) > 1 else (set(), 0.0)
        if len(top) < MIN_INLIERS or top_iou < IOU_MIN:
            return None
        if len(top) >= MARGIN * max(len(runner_up), 1):
            return Reading(value=top_value, confidence=0.95, reader=self.name)
        # Adversarial rescoring: a close inlier contest is settled by which
        # glyph shape actually fits the query, not by shared strokes.
        if top_iou >= IOU_MARGIN * max(runner_iou, 0.05):
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
