"""Frame sources: camera devices, network streams, and video files."""
from pathlib import Path
from typing import Iterator, Protocol

import cv2
import numpy as np


class FrameSource(Protocol):
    def frames(self) -> Iterator[np.ndarray]: ...


class VideoFileSource:
    """Reads frames from a video file (used in tests and offline debugging)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def frames(self) -> Iterator[np.ndarray]:
        cap = cv2.VideoCapture(str(self.path))
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    return
                yield frame
        finally:
            cap.release()


class CameraSource:
    """Live camera: int device index (Continuity Camera / USB) or stream URL."""

    def __init__(self, spec: int | str):
        self.spec = spec

    def frames(self) -> Iterator[np.ndarray]:
        cap = cv2.VideoCapture(self.spec)
        if not cap.isOpened():
            raise RuntimeError(f"could not open camera source {self.spec!r}")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    return
                yield frame
        finally:
            cap.release()
