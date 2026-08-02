"""Persist every roll (frame + prediction) as a labeled-training-data candidate."""
import json
import time
from itertools import count
from pathlib import Path

import cv2
import numpy as np

from .readers import Reading


class RollLogger:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.frames_dir = self.root / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.rows_path = self.root / "rolls.jsonl"
        self._seq = count()

    def log(self, frame: np.ndarray, reading: Reading | None, context: str | None = None) -> str:
        roll_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{next(self._seq):03d}"
        cv2.imwrite(str(self.frames_dir / f"{roll_id}.png"), frame)
        row = {
            "id": roll_id,
            "predicted": reading.value if reading else None,
            "confidence": reading.confidence if reading else None,
            "reader": reading.reader if reading else None,
            "context": context,
            "confirmed": None,
        }
        with self.rows_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return roll_id

    def confirm(self, roll_id: str, value: int) -> None:
        with self.rows_path.open("a") as f:
            f.write(json.dumps({"id": roll_id, "event": "confirm", "confirmed": value}) + "\n")

    def frame_path(self, roll_id: str) -> Path:
        return self.frames_dir / f"{roll_id}.png"
