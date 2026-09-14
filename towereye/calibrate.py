"""App-driven calibration: save per-face templates from the live feed while
the watch runs, and grow the keypoint pool without a restart."""
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .dice import AUTO, FACES, normalize
from .keypoints import save_template


class LatestFrame:
    """Holds the most recent camera frame for the calibrator to grab."""

    def __init__(self):
        self.frame: np.ndarray | None = None

    def tee(self, frames):
        for frame in frames:
            self.frame = frame
            yield frame


class Calibrator:
    REQUESTS = ("templates", "calibrate_start", "calibrate_save", "calibrate_stop")

    def __init__(self, template_root: str | Path, keypoints=None,
                 latest: Callable[[], np.ndarray | None] = lambda: None):
        self.root = Path(template_root)
        self.keypoints = keypoints  # KeypointReader to grow live (optional)
        self.latest = latest
        self.die: str | None = None

    @property
    def active(self) -> bool:
        return self.die is not None

    def counts(self, die: str) -> dict[str, int]:
        faces = FACES[die]
        pool = self.root / die
        return {str(v): len(list(pool.glob(f"{v}_*.png"))) for v in range(1, faces + 1)}

    def pools(self) -> dict:
        return {"type": "templates", "pools": {die: self.counts(die) for die in FACES}}

    def start(self, die) -> dict:
        canon = normalize(die)
        if canon is None or canon == AUTO:
            return {"type": "calibrate_error", "reason": f"pick a specific die to calibrate, not {die!r}"}
        self.die = canon
        return self._state()

    def stop(self) -> dict:
        self.die = None
        return self._state()

    def save(self, value) -> dict:
        if self.die is None:
            return {"type": "calibrate_error", "reason": "not calibrating"}
        try:
            value = int(value)
        except (TypeError, ValueError):
            return {"type": "calibrate_error", "reason": f"bad face value {value!r}"}
        if not 1 <= value <= FACES[self.die]:
            return {"type": "calibrate_error", "reason": f"{self.die} has no face {value}"}
        frame = self.latest()
        if frame is None:
            return {"type": "calibrate_error", "reason": "no camera frame yet"}
        path = save_template(frame, value, self.root / self.die)
        if path is None:
            return {"type": "calibrate_error", "reason": "no die found in frame - check placement and light"}
        if self.keypoints is not None:
            img = cv2.imread(str(path))
            if img is not None:
                self.keypoints.add_template(img, value, self.die)
        return {"type": "template_saved", "die": self.die, "value": value,
                "path": str(path), "counts": self.counts(self.die)}

    def _state(self) -> dict:
        if self.die is None:
            return {"type": "calibrating", "die": None}
        return {"type": "calibrating", "die": self.die, "faces": FACES[self.die],
                "counts": self.counts(self.die)}

    def handle(self, msg: dict) -> dict | None:
        kind = msg.get("type")
        if kind == "templates":
            return self.pools()
        if kind == "calibrate_start":
            return self.start(msg.get("die"))
        if kind == "calibrate_save":
            return self.save(msg.get("value"))
        if kind == "calibrate_stop":
            return self.stop()
        return None
