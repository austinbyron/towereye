import urllib.error
import urllib.request

import numpy as np

from towereye.stream import FramePublisher, StreamServer


def _frame(w=1920, h=1080):
    f = np.zeros((h, w, 3), dtype=np.uint8)
    f[:, : w // 2] = (255, 120, 100)
    return f


def test_publisher_downscales_and_rate_limits():
    pub = FramePublisher(width=960, max_fps=10)
    assert pub.publish(_frame(), now=0.0)
    assert not pub.publish(_frame(), now=0.05)   # too soon
    assert pub.publish(_frame(), now=0.2)
    jpeg = pub.latest()
    assert jpeg[:2] == b"\xff\xd8"                # JPEG magic
    import cv2
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == 960 and decoded.shape[0] == 540


def test_server_serves_latest_frame_and_mjpeg_boundary():
    pub = FramePublisher()
    server = StreamServer(pub, port=0)
    server.start_in_thread()
    try:
        url = f"http://127.0.0.1:{server.port}"
        try:
            urllib.request.urlopen(f"{url}/frame.jpg", timeout=2)
            assert False, "expected 503 before any frame"
        except urllib.error.HTTPError as err:
            assert err.code == 503
        pub.publish(_frame(), now=0.0)
        with urllib.request.urlopen(f"{url}/frame.jpg", timeout=2) as resp:
            assert resp.headers["Content-Type"] == "image/jpeg"
            assert resp.read()[:2] == b"\xff\xd8"
        with urllib.request.urlopen(f"{url}/stream.mjpg", timeout=2) as resp:
            assert "multipart/x-mixed-replace" in resp.headers["Content-Type"]
            head = resp.readline()
            assert head.startswith(b"--towereyeframe")
    finally:
        server.stop()
