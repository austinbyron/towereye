"""Locate the die and crop to its top face.

Looking straight down, the top face sits over the die's centroid; side-face
numerals project outward. A tight crop around the blue blob's centroid leaves
readers only the top-face numeral to consider.
"""
import cv2
import numpy as np

from .presence import HSV_HI, HSV_LO, MIN_DIE_RADIUS

CROP_SCALE = 0.75   # crop half-size as a fraction of the blob's equivalent radius
MIN_RADIUS = MIN_DIE_RADIUS


def die_blob(frame: np.ndarray) -> tuple[float, float, float] | None:
    """(cx, cy, equivalent radius) of the largest blue blob, or None."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LO, HSV_HI)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    cx, cy = centroids[i]
    radius = float(np.sqrt(stats[i, cv2.CC_STAT_AREA] / np.pi))
    if radius < MIN_RADIUS:
        return None
    return float(cx), float(cy), radius


NEUTRAL_FLOOR = 40       # never demand less neutrality than the original absolute cutoff
NEUTRAL_BODY_FRAC = 0.5


def lettering(img: np.ndarray) -> np.ndarray:
    """Gray image masked to the white numerals; body, swirl, and glare dropped.

    Paint is color-neutral (B-R near zero) while the blue body and its
    blue-tinted specular sheen are not; brightness adapts per crop, and a
    component-size filter sheds specks and glare sheets.
    """
    b, g, r = cv2.split(img.astype(np.int16))
    blue_shift = b - r
    bright = np.minimum(np.minimum(b, g), r)
    # Paint is far less blue-shifted than the body, but the absolute shift
    # depends on the room's white balance (numerals read B-R~25 in one room,
    # ~64 under warm lamps), so split the crop's own shift distribution:
    # Otsu between the paint and body modes, capped below the body median.
    shift8 = np.clip(blue_shift, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(shift8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cutoff = min(otsu, NEUTRAL_BODY_FRAC * float(np.median(blue_shift)))
    neutral = blue_shift < max(cutoff, NEUTRAL_FLOOR)
    if neutral.sum() < 50:
        return np.zeros(img.shape[:2], np.uint8)
    thresh = max(60, int(np.percentile(bright[neutral], 75)) - 30)
    mask = (neutral & (bright > thresh)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    area = img.shape[0] * img.shape[1]
    keep = np.zeros_like(mask)
    for i in range(1, count):
        if 15 <= stats[i, cv2.CC_STAT_AREA] <= 0.12 * area:
            keep[labels == i] = 255
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    keep = cv2.dilate(keep, np.ones((5, 5), np.uint8))
    return cv2.bitwise_and(gray, gray, mask=keep)


def _window(frame: np.ndarray, cx: float, cy: float, radius: float) -> np.ndarray:
    half = int(CROP_SCALE * radius)
    h, w = frame.shape[:2]
    x0, x1 = max(0, int(cx) - half), min(w, int(cx) + half)
    y0, y1 = max(0, int(cy) - half), min(h, int(cy) + half)
    return frame[y0:y1, x0:x1]


def topface_crop(frame: np.ndarray) -> np.ndarray | None:
    blob = die_blob(frame)
    if blob is None:
        return None
    cx, cy, radius = blob
    crop = _window(frame, cx, cy, radius)
    if not crop.size:
        return None
    # second pass: the blob centroid drifts when the die is half-shadowed;
    # re-center the window on the central numeral pixels (the top face)
    target = _central_numeral(crop)
    if target is not None:
        h, w = crop.shape[:2]
        dx, dy = target[0] - w / 2, target[1] - h / 2
        # only intervene on real drift: small shifts mean the crop was fine,
        # and nudging those pulls toward adjacent numerals
        if 0.08 * w < np.hypot(dx, dy) < 0.5 * radius:
            recentered = _window(frame, cx + dx, cy + dy, radius)
            if recentered.size:
                crop = recentered
    return crop


def _central_numeral(crop: np.ndarray) -> tuple[float, float] | None:
    """Centroid of the largest lettering cluster near the crop center.

    Digits of one numeral merge under dilation while separate faces' numerals
    stay apart, so the biggest central cluster is the top-face numeral — using
    the mean of ALL lettering pixels instead can land between two numerals.
    """
    marks = lettering(crop)
    h, w = crop.shape[:2]
    k = max(3, int(0.12 * h))
    merged = cv2.dilate((marks > 0).astype(np.uint8) * 255, np.ones((k, k), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(merged)
    best = None
    for i in range(1, count):
        cx, cy = centroids[i]
        if abs(cx - w / 2) > 0.35 * w or abs(cy - h / 2) > 0.35 * h:
            continue
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 30:
            continue
        if best is None or area > best[0]:
            best = (area, cx, cy)
    return (best[1], best[2]) if best else None


def sharpness(frame: np.ndarray) -> float:
    """Focus score (Laplacian variance) of the top-face region, for picking
    the crispest post-settle frame while the camera refocuses."""
    crop = topface_crop(frame)
    target = crop if crop is not None else frame
    gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
