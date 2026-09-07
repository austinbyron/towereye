"""Localhost MJPEG stream of the watch's own frames.

The watch process owns the Continuity Camera, and macOS won't hand OBS a
second handle on the same device, so the watch republishes what it sees:
`GET /stream.mjpg` is a multipart MJPEG feed and `GET /frame.jpg` the latest
still. OBS loads the overlay page, which layers the result graphics over
this feed, as a single browser source.
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

STREAM_WIDTH = 960      # downscale for the browser source; the reader keeps full res
JPEG_QUALITY = 80
MAX_FPS = 15.0
BOUNDARY = "towereyeframe"


class FramePublisher:
    """Holds the most recent JPEG; `publish` is cheap enough to call per frame."""

    def __init__(self, width: int = STREAM_WIDTH, max_fps: float = MAX_FPS):
        self.width = width
        self._min_interval = 1.0 / max_fps
        self._jpeg: bytes | None = None
        self._seq = 0
        self._last = float("-inf")
        self._cond = threading.Condition()

    def publish(self, frame: np.ndarray, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if now - self._last < self._min_interval:
            return False
        h, w = frame.shape[:2]
        if w > self.width:
            frame = cv2.resize(frame, (self.width, int(h * self.width / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return False
        with self._cond:
            self._jpeg = buf.tobytes()
            self._seq += 1
            self._last = now
            self._cond.notify_all()
        return True

    def latest(self) -> bytes | None:
        with self._cond:
            return self._jpeg

    def wait_next(self, seen: int, timeout: float = 1.0) -> tuple[int, bytes | None]:
        """Block until a frame newer than `seen` exists (or timeout)."""
        with self._cond:
            if self._seq == seen:
                self._cond.wait(timeout)
            return self._seq, self._jpeg


class _Handler(BaseHTTPRequestHandler):
    publisher: FramePublisher  # set on the server class

    def log_message(self, *_):  # keep the watch console clean
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/frame.jpg":
            jpeg = self.publisher.latest()
            if jpeg is None:
                self.send_response(503)
                self._cors()
                self.end_headers()
                return
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.end_headers()
            self.wfile.write(jpeg)
            return
        if path == "/stream.mjpg":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.end_headers()
            seen = 0
            try:
                while True:
                    seen, jpeg = self.publisher.wait_next(seen)
                    if jpeg is None:
                        continue
                    self.wfile.write(
                        f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
                    )
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        self.send_response(404)
        self._cors()
        self.end_headers()


class StreamServer:
    def __init__(self, publisher: FramePublisher, port: int = 8778, host: str = "127.0.0.1"):
        self.publisher = publisher
        handler = type("Handler", (_Handler,), {"publisher": publisher})
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread: threading.Thread | None = None

    def start_in_thread(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
