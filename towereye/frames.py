"""Frame sources: camera devices, network streams, and video files."""
import time
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
    """Live camera: int device index (Continuity Camera / USB) or stream URL.

    Continuity Camera drops frames (and sometimes the whole device) whenever
    another app enumerates cameras, e.g. OBS starting up. A dropped read used
    to end the session silently; now the source reopens the device and keeps
    trying for `reconnect_seconds` before giving up.
    """

    def __init__(self, spec: int | str, reconnect_seconds: float = 120.0,
                 opener=cv2.VideoCapture, sleep=time.sleep, log=print):
        self.spec = spec
        self.reconnect_seconds = reconnect_seconds
        self._open = opener
        self._sleep = sleep
        self._log = log

    def frames(self) -> Iterator[np.ndarray]:
        cap = self._open(self.spec)
        if not cap.isOpened():
            # a camera just released by another process (or a phone waking
            # up) can take a few seconds to become openable again
            cap.release()
            self._log(f"camera {self.spec!r} not available yet; waiting for it...")
            cap = self._reconnect()
            if cap is None:
                raise RuntimeError(f"could not open camera source {self.spec!r}")
        try:
            while True:
                ok, frame = cap.read()
                if ok:
                    yield frame
                    continue
                cap.release()
                cap = self._reconnect()
                if cap is None:
                    self._log(f"camera {self.spec!r} did not come back within {self.reconnect_seconds:.0f}s; stopping")
                    return
        finally:
            cap.release() if cap is not None else None

    def _reconnect(self):
        self._log(f"camera {self.spec!r} dropped a frame; reconnecting...")
        deadline = time.monotonic() + self.reconnect_seconds
        while time.monotonic() < deadline:
            self._sleep(1.0)
            cap = self._open(self.spec)
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    self._log(f"camera {self.spec!r} is back")
                    return cap
            cap.release()
        return None
