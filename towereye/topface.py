"""Locate the die and crop to its top face.

Looking straight down, the top face sits over the die's centroid; side-face
numerals project outward. A tight crop around the blue blob's centroid leaves
readers only the top-face numeral to consider.
"""
import cv2
import numpy as np

from .presence import HSV_HI, HSV_LO

CROP_SCALE = 0.75   # crop half-size as a fraction of the blob's equivalent radius
MIN_RADIUS = 35     # px; the die is r>=50 in every real session, junk blobs < 30


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


def topface_crop(frame: np.ndarray) -> np.ndarray | None:
    blob = die_blob(frame)
    if blob is None:
        return None
    cx, cy, radius = blob
    half = int(CROP_SCALE * radius)
    h, w = frame.shape[:2]
    x0, x1 = max(0, int(cx) - half), min(w, int(cx) + half)
    y0, y1 = max(0, int(cy) - half), min(h, int(cy) + half)
    crop = frame[y0:y1, x0:x1]
    return crop if crop.size else None


def sharpness(frame: np.ndarray) -> float:
    """Focus score (Laplacian variance) of the top-face region, for picking
    the crispest post-settle frame while the camera refocuses."""
    crop = topface_crop(frame)
    target = crop if crop is not None else frame
    gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
