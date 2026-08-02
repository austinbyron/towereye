"""Cheap die-presence gate: a settled frame only counts if a blue die is in the tray."""
import cv2
import numpy as np

# HSV band for the blue dice; the S/V floors reject the gray tower and shadows,
# tuned against real rig frames: hand-shadow blobs on the dark tray measure
# S ~104-111, real dice S ~150-180 (even dim no-LED frames), so S >= 130.
HSV_LO = (95, 130, 50)
HSV_HI = (135, 255, 255)
CENTER_CROP = 0.6     # central fraction of the frame treated as the tray interior
MIN_DIE_RADIUS = 35   # px, absolute: dice are r>=50 in every real session, junk < 30


def die_present(frame: np.ndarray, center_crop: float = CENTER_CROP) -> bool:
    h, w = frame.shape[:2]
    lo = (1 - center_crop) / 2
    hi = 1 - lo
    crop = frame[int(h * lo) : int(h * hi), int(w * lo) : int(w * hi)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LO, HSV_HI)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return False
    return int(stats[1:, cv2.CC_STAT_AREA].max()) >= np.pi * MIN_DIE_RADIUS**2
