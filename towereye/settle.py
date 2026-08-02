"""Motion-based settle detection: fire once when a thrown die comes to rest."""
from dataclasses import dataclass
from enum import Enum, auto

import cv2
import numpy as np


class SettleState(Enum):
    WAITING = auto()   # no motion observed yet (empty tray / idle)
    MOTION = auto()    # die currently moving
    SETTLED = auto()   # motion stopped after motion — frame attached
    TIMEOUT = auto()   # motion never stopped within timeout_frames
    DONE = auto()      # already settled/timed out; reset() to re-arm


@dataclass
class SettleResult:
    state: SettleState
    frame: np.ndarray | None = None


DIFF_INTENSITY = 15  # per-pixel gray delta that counts as a changed pixel


class SettleDetector:
    """Motion = fraction of pixels changing meaningfully, not mean frame delta:
    a die spinning in place moves ~1-2% of pixels hard, which a whole-frame
    mean washes out but a changed-pixel fraction catches."""

    def __init__(
        self,
        motion_threshold: float = 0.003,
        settle_frames: int = 15,
        timeout_frames: int = 300,
    ):
        self.motion_threshold = motion_threshold
        self.settle_frames = settle_frames
        self.timeout_frames = timeout_frames
        self.reset()

    def reset(self) -> None:
        self._prev: np.ndarray | None = None
        self._motion_seen = False
        self._still_count = 0
        self._frames_since_motion = 0
        self._done = False

    def _prep(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def feed(self, frame: np.ndarray) -> SettleResult:
        if self._done:
            return SettleResult(SettleState.DONE)
        cur = self._prep(frame)
        if self._prev is None:
            self._prev = cur
            return SettleResult(SettleState.WAITING)
        diff = float((cv2.absdiff(cur, self._prev) > DIFF_INTENSITY).mean())
        self._prev = cur

        if not self._motion_seen:
            if diff > self.motion_threshold:
                self._motion_seen = True
                self._frames_since_motion = 0
                return SettleResult(SettleState.MOTION)
            return SettleResult(SettleState.WAITING)

        self._frames_since_motion += 1
        if self._frames_since_motion > self.timeout_frames:
            self._done = True
            return SettleResult(SettleState.TIMEOUT)

        if diff > self.motion_threshold:
            self._still_count = 0
            return SettleResult(SettleState.MOTION)

        self._still_count += 1
        if self._still_count >= self.settle_frames:
            self._done = True
            return SettleResult(SettleState.SETTLED, frame=frame)
        return SettleResult(SettleState.MOTION)
