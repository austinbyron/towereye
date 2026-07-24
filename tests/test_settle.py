import numpy as np

from towereye.settle import SettleDetector, SettleState


def _blank(w=64, h=48):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _with_square(x, w=64, h=48):
    frame = _blank(w, h)
    frame[10:30, x : x + 20] = 255
    return frame


def _feed_all(det, frames):
    return [det.feed(f) for f in frames]


def test_static_scene_never_settles():
    det = SettleDetector(settle_frames=3, timeout_frames=100)
    results = _feed_all(det, [_blank() for _ in range(20)])
    assert all(r.state == SettleState.WAITING for r in results)


def test_motion_then_still_settles_once():
    det = SettleDetector(settle_frames=3, timeout_frames=100)
    moving = [_with_square(x) for x in range(0, 30, 6)]  # die tumbling
    still = [_with_square(24) for _ in range(10)]         # die at rest
    results = _feed_all(det, moving + still)
    # NB: don't use list.index()/== on SettleResult - dataclass equality on the
    # numpy frame field raises "truth value ambiguous". Compare by state only.
    settled_indices = [i for i, r in enumerate(results) if r.state == SettleState.SETTLED]
    assert len(settled_indices) == 1
    assert results[settled_indices[0]].frame is not None
    # after settling the detector stays quiet (DONE) until reset
    assert all(r.state != SettleState.MOTION for r in results[settled_indices[0] + 1 :])


def test_endless_motion_times_out():
    det = SettleDetector(settle_frames=3, timeout_frames=10)
    frames = [_with_square((i * 7) % 40) for i in range(30)]
    states = [det.feed(f).state for f in frames]
    assert SettleState.TIMEOUT in states
    assert SettleState.SETTLED not in states


def test_reset_allows_second_throw():
    det = SettleDetector(settle_frames=3, timeout_frames=100)
    _feed_all(det, [_with_square(x) for x in range(0, 30, 6)])
    _feed_all(det, [_with_square(24) for _ in range(10)])
    det.reset()
    results = _feed_all(
        det,
        [_with_square(x) for x in range(0, 30, 6)] + [_with_square(24)] * 10,
    )
    assert any(r.state == SettleState.SETTLED for r in results)
