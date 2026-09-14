import os

import numpy as np
import pytest

from towereye.cli import _load_dotenv, _zoom_frames, run_watch
from towereye.readers import Reading
from towereye.settle import SettleDetector


class FixedReader:
    name = "fixed"

    def __init__(self, value):
        self._value = value

    def read(self, frame):
        return Reading(value=self._value, confidence=1.0, reader=self.name)


class ListLogger:
    def __init__(self):
        self.entries = []
        self.contexts = []

    def log(self, frame, reading, context=None):
        self.entries.append(reading)
        self.contexts.append(context)
        return "test-id"


def _throw_frames(color=(255, 120, 100)):
    def square(x):
        f = np.zeros((160, 240, 3), dtype=np.uint8)
        f[45:115, x : x + 70] = color
        return f

    return [square(x) for x in range(0, 72, 12)] + [square(60)] * 10


def test_run_watch_reports_and_logs_settled_roll():
    events = []
    logger = ListLogger()
    run_watch(
        frames=iter(_throw_frames()),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        emit=events.append,
    )
    assert any(e["type"] == "result" and e["value"] == 7 for e in events)
    assert len(logger.entries) == 1
    assert logger.entries[0].value == 7


def test_run_watch_skips_settles_without_a_die():
    events = []
    logger = ListLogger()
    # a gray blob settles (hand / empty-tray motion), then a blue die settles
    frames = _throw_frames(color=(128, 128, 128)) + _throw_frames()
    run_watch(
        frames=iter(frames),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        emit=events.append,
    )
    assert len(logger.entries) == 1  # gray settle neither reported nor logged
    assert sum(1 for e in events if e["type"] == "result" and e["value"] == 7) == 1


def test_load_dotenv_fills_missing_vars_without_clobbering(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TOWEREYE_TEST_KEY=abc\n# comment\n\nTOWEREYE_TEST_SET=new\nTOWEREYE_TEST_EMPTY=\n")
    monkeypatch.setenv("TOWEREYE_TEST_SET", "old")
    try:
        _load_dotenv(env)
        assert os.environ["TOWEREYE_TEST_KEY"] == "abc"
        assert os.environ["TOWEREYE_TEST_SET"] == "old"  # real env wins
        assert "TOWEREYE_TEST_EMPTY" not in os.environ  # unfilled seed line ignored
    finally:
        os.environ.pop("TOWEREYE_TEST_KEY", None)


def test_load_dotenv_missing_file_is_noop(tmp_path):
    _load_dotenv(tmp_path / ".env")


class RecordingReader(FixedReader):
    def __init__(self, value):
        super().__init__(value)
        self.frames = []

    def read(self, frame):
        self.frames.append(frame)
        return super().read(frame)


def _die_square(x, sharp=False):
    """A die-sized (70px, r~40) blob so die_blob() sees it, in a 160x240 frame."""
    f = np.zeros((160, 240, 3), dtype=np.uint8)
    f[45:115, x : x + 70] = (255, 120, 100)
    if sharp:
        f[72:88, x + 15 : x + 55] = (255, 255, 255)  # crisp numeral detail
    return f


def test_run_watch_reads_the_sharpest_post_settle_frame():
    import cv2

    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    blurred = [cv2.GaussianBlur(f, (21, 21), 8) for f in throw]
    sharp_tail = [_die_square(60, sharp=True)] * 8  # focus catches up, die unmoved
    reader = RecordingReader(7)
    run_watch(
        frames=iter(blurred + sharp_tail),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=reader,
        logger=ListLogger(),
        emit=lambda _: None,
    )
    assert reader.frames  # a roll was read
    from towereye.topface import sharpness

    assert sharpness(reader.frames[0]) > sharpness(blurred[-1])


def test_run_watch_ignores_post_settle_frames_where_die_moved():
    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    # after settling at x=60, the die is picked up: sharper frames, wrong place
    grabbed = [_die_square(160, sharp=True)] * 15
    reader = RecordingReader(7)
    run_watch(
        frames=iter(throw + grabbed),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=reader,
        logger=ListLogger(),
        emit=lambda _: None,
    )
    assert reader.frames
    from towereye.topface import die_blob

    cx, _, _ = die_blob(reader.frames[0])
    assert abs(cx - 95) < 8  # the settled die (center x=95), not the moved one (x=195)


def test_run_watch_asks_for_reroll_when_die_clipped_at_frame_edge():
    events = []
    logger = ListLogger()

    def edge_square(x):
        f = np.zeros((160, 240, 3), dtype=np.uint8)
        f[100:160, x : x + 80] = (255, 120, 100)  # die at the bottom boundary
        return f

    frames = [edge_square(x) for x in range(0, 72, 12)] + [edge_square(60)] * 10
    run_watch(
        frames=iter(frames),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        emit=events.append,
    )
    assert any(e["type"] == "reroll" for e in events)
    assert not logger.entries  # never read, never logged


def test_zoom_frames_center_crops():
    f = np.zeros((90, 120, 3), dtype=np.uint8)
    f[30:60, 40:80] = (255, 120, 100)  # central third survives any zoom <= 3x
    (out,) = _zoom_frames(iter([f]), 1.5)
    assert out.shape == (60, 80, 3)
    assert (out[15:45, 20:60] == (255, 120, 100)).all()


def test_zoom_frames_at_1x_is_identity():
    f = np.arange(90 * 120 * 3, dtype=np.uint8).reshape(90, 120, 3)
    (out,) = _zoom_frames(iter([f]), 1.0)
    assert out is f


def test_run_watch_emits_result_event():
    events = []
    logger = ListLogger()
    run_watch(
        frames=iter(_throw_frames()),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        emit=events.append,
    )
    results = [e for e in events if e["type"] == "result"]
    assert len(results) == 1
    assert results[0]["value"] == 7
    assert results[0]["reader"] == "fixed"
    assert results[0]["roll_id"] == "test-id"  # ListLogger returns "test-id"


def test_run_watch_dedupes_resettle_of_unmoved_die():
    events = []
    logger = ListLogger()
    # roll settles, then the same die re-settles (shadow flicker), then moves
    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    resettle = [_die_square(60)] * 3 + [_die_square(61)] * 2 + [_die_square(60)] * 10
    run_watch(
        frames=iter(throw + resettle),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        emit=events.append,
    )
    assert len([e for e in events if e["type"] == "result"]) == 1
    assert len(logger.entries) == 1


def test_run_watch_never_rereads_a_die_that_stays_put():
    events = []
    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    # lights change / tower vibration: repeated re-settles in the same spot
    flicker = ([_die_square(61)] * 2 + [_die_square(60)] * 10) * 4
    run_watch(
        frames=iter(throw + flicker),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=ListLogger(),
        emit=events.append,
    )
    assert len([e for e in events if e["type"] == "result"]) == 1


def test_run_watch_reports_again_after_die_leaves_and_returns():
    events = []
    empty = np.zeros((160, 240, 3), dtype=np.uint8)
    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    # hand drags the die out (motion, then an empty tray settles), then a new
    # roll lands in the same spot; the still lead-in outlasts POST_SETTLE_FRAMES
    lifted = [_die_square(60)] * 10 + [_die_square(x) for x in range(48, -1, -12)] + [empty] * 30
    rethrow = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 10
    run_watch(
        frames=iter(throw + lifted + rethrow),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=ListLogger(),
        emit=events.append,
    )
    assert len([e for e in events if e["type"] == "result"]) == 2


def test_format_event_matches_console_lines():
    from towereye.cli import format_event

    assert format_event(
        {"type": "result", "roll_id": "x", "value": 17, "confidence": 0.95, "reader": "keypoints"}
    ) == "You rolled 17 (keypoints, 0.95)"
    assert format_event({"type": "unread", "roll_id": "x"}) == (
        "Could not read the die after resampling - reroll"
    )
    assert format_event({"type": "reroll", "reason": "tray-edge"}) == (
        "Die is at the tray edge - reroll"
    )
    assert format_event({"type": "timeout"}) == (
        "Die never settled (cocked or bounced out?) - re-roll"
    )


def test_fan_out_prints_and_broadcasts(capsys):
    from towereye.cli import _fan_out

    class FakeHub:
        def __init__(self):
            self.events = []

        def broadcast(self, e):
            self.events.append(e)

    hub = FakeHub()
    emit = _fan_out(hub, ListLogger())
    event = {"type": "result", "roll_id": "r", "value": 4, "confidence": 0.95, "reader": "keypoints"}
    emit(event)
    assert hub.events == [event]
    assert "You rolled 4" in capsys.readouterr().out


def test_fan_out_without_hub_still_prints(capsys):
    from towereye.cli import _fan_out

    emit = _fan_out(None, ListLogger())
    emit({"type": "timeout"})
    assert "never settled" in capsys.readouterr().out


def test_confirm_harvests_template_until_cap(tmp_path):
    import cv2

    from towereye.cli import _harvest_on_confirm
    from towereye.datalog import RollLogger

    logger = RollLogger(tmp_path / "dataset")
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    frame[110:190, 110:190] = (255, 120, 100)  # a die blob so save_template crops
    logger.log(frame, None)  # writes dataset/frames/<id>.png
    roll_id = __import__("json").loads(
        (tmp_path / "dataset" / "rolls.jsonl").read_text().splitlines()[0]
    )["id"]

    tdir = tmp_path / "templates"
    on_confirm = _harvest_on_confirm(logger, template_dir=tdir, max_per_face=1)
    on_confirm(roll_id, 17)
    assert len(list(tdir.glob("17_*.png"))) == 1
    on_confirm(roll_id, 17)  # cap reached: no second template
    assert len(list(tdir.glob("17_*.png"))) == 1
    # and the confirmation rows were written regardless
    rows = (tmp_path / "dataset" / "rolls.jsonl").read_text().splitlines()
    assert sum('"event": "confirm"' in r for r in rows) == 2


def test_confirm_with_missing_frame_only_logs(tmp_path):
    from towereye.cli import _harvest_on_confirm
    from towereye.datalog import RollLogger

    logger = RollLogger(tmp_path / "dataset")
    on_confirm = _harvest_on_confirm(logger, template_dir=tmp_path / "templates")
    on_confirm("no-such-roll", 4)  # must not raise
    assert '"confirmed": 4' in (tmp_path / "dataset" / "rolls.jsonl").read_text()


def test_run_watch_resamples_fresh_frames_before_giving_up():
    class FlakyChain:
        def __init__(self):
            self.calls = 0

        def read(self, frame):
            self.calls += 1
            return Reading(value=11, confidence=0.95, reader="k") if self.calls == 2 else None

    events = []
    chain = FlakyChain()
    # long still tail so the resample rounds have stable frames to pull
    throw = [_die_square(x) for x in range(0, 72, 12)] + [_die_square(60)] * 60
    run_watch(
        frames=iter(throw),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=chain,
        logger=ListLogger(),
        emit=events.append,
    )
    results = [e for e in events if e["type"] == "result"]
    assert [e["value"] for e in results] == [11]
    assert chain.calls == 2
    assert not [e for e in events if e["type"] == "unread"]


def test_probe_cameras_returns_thumbnails_for_openable_indices():
    from towereye.cli import probe_cameras

    class Cap:
        def __init__(self, ok):
            self.ok = ok
        def isOpened(self):
            return self.ok
        def read(self):
            return (True, np.zeros((720, 1280, 3), np.uint8)) if self.ok else (False, None)
        def release(self):
            pass

    cams = probe_cameras(max_index=3, warmup_seconds=0.01, opener=lambda i: Cap(i != 1))
    assert [c["index"] for c in cams] == [0, 2]
    assert cams[0]["width"] == 1280 and cams[0]["thumbnail"].startswith("data:image/jpeg;base64,")


def test_run_watch_stamps_result_events_with_the_current_die():
    events = []
    logger = ListLogger()
    run_watch(
        frames=iter(_throw_frames()),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        emit=events.append,
        die=lambda: "d8",
    )
    results = [e for e in events if e["type"] == "result"]
    assert results[0]["die"] == "d8"
    assert logger.contexts == ["d8"]


def test_harvest_pool_follows_the_selected_die(tmp_path):
    from towereye.cli import _harvest_on_confirm
    from towereye.datalog import RollLogger

    logger = RollLogger(tmp_path / "dataset")
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    frame[110:190, 110:190] = (255, 120, 100)
    logger.log(frame, None)
    roll_id = __import__("json").loads(
        (tmp_path / "dataset" / "rolls.jsonl").read_text().splitlines()[0]
    )["id"]
    die = ["auto"]
    on_confirm = _harvest_on_confirm(logger, template_dir=tmp_path / "templates", die=lambda: die[0])
    on_confirm(roll_id, 6)
    assert (tmp_path / "templates" / "d20" / "6_000.png").exists()  # auto harvests into the d20 pool
    die[0] = "d8"
    on_confirm(roll_id, 6)
    assert (tmp_path / "templates" / "d8" / "6_000.png").exists()


def test_watch_parser_accepts_a_die_flag():
    from towereye.cli import _parser

    assert _parser().parse_args(["watch", "--die", "D8"]).die == "d8"
    assert _parser().parse_args(["watch"]).die == "auto"
    with pytest.raises(SystemExit):
        _parser().parse_args(["watch", "--die", "d7"])


def test_run_watch_reports_nothing_while_paused():
    events = []
    paused = [True]
    frames = list(_throw_frames()) + list(_throw_frames())
    n = len(frames) // 2

    def gen():
        for i, f in enumerate(frames):
            if i == n:
                paused[0] = False  # calibration ends halfway: second throw must report
            yield f

    run_watch(
        frames=gen(),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=ListLogger(),
        emit=events.append,
        paused=lambda: paused[0],
    )
    assert [e["type"] for e in events if e["type"] == "result"] == ["result"]


def test_cameras_json_reports_denied_access(monkeypatch, capsys):
    import json

    from towereye import cli

    monkeypatch.setattr("towereye.camera_access.ensure_camera_access", lambda log=print: False)
    monkeypatch.setattr(cli, "probe_cameras", lambda n: (_ for _ in ()).throw(AssertionError("must not probe")))
    rc = cli.main(["cameras", "--json"])
    assert rc == 3
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "denied" in out["error"]


def test_cameras_json_is_clean_when_allowed(monkeypatch, capsys):
    import json

    from towereye import cli

    monkeypatch.setattr("towereye.camera_access.ensure_camera_access", lambda log=print: (log("granted"), True)[1])
    monkeypatch.setattr(cli, "probe_cameras", lambda n: [{"index": 0, "width": 1, "height": 1}])
    assert cli.main(["cameras", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == [{"index": 0, "width": 1, "height": 1}]  # stdout is pure JSON
    assert "granted" in captured.err
