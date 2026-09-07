"""towereye CLI: watch the tray, read stills, capture frames for the golden set."""
import argparse
import itertools
import os
import sys
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from .datalog import RollLogger
from .frames import CameraSource, VideoFileSource
from .presence import die_present
from .readers import ReaderChain
from .settle import SettleDetector, SettleState
from .topface import die_blob, sharpness

# frames to pull after a settle so autofocus can catch up (~0.5s at 30fps);
# the sharpest STABLE one is read
POST_SETTLE_FRAMES = 15
# when no reader is confident, pull fresh frames and try again this many
# times (autofocus/glare often clears in the next half second) before
# asking for a reroll
RESAMPLE_ROUNDS = 2

# A die that re-settles in the same spot (shadow flicker, lights changing,
# tower vibration) is never re-reported; only its leaving the tray re-arms.


def _at_frame_edge(blob: tuple[float, float, float], frame: np.ndarray) -> bool:
    cx, cy, r = blob
    h, w = frame.shape[:2]
    margin = 1.15 * r
    return cx < margin or cy < margin or cx > w - margin or cy > h - margin


def _die_unmoved(ref: tuple[float, float, float], frame: np.ndarray) -> bool:
    """True if the frame's die blob matches the settle frame's position/size —
    guards against reading a frame where the hand already lifted the die."""
    blob = die_blob(frame)
    if blob is None:
        return False
    (rx, ry, rr), (cx, cy, cr) = ref, blob
    return abs(cx - rx) <= 0.5 * rr and abs(cy - ry) <= 0.5 * rr and 0.7 <= cr / rr <= 1.4


def _watch_gate(frame: np.ndarray) -> bool:
    # full-frame gate: the S floor and absolute die-size floor carry junk
    # rejection, and a center restriction silently drops tray-edge dice
    return die_present(frame, center_crop=1.0)


def format_event(event: dict) -> str:
    """Convert a structured event dict to a console line."""
    kind = event["type"]
    if kind == "result":
        return f"You rolled {event['value']} ({event['reader']}, {event['confidence']:.2f})"
    if kind == "unread":
        return "Could not read the die after resampling - reroll"
    if kind == "reroll":
        return "Die is at the tray edge - reroll"
    return "Die never settled (cocked or bounced out?) - re-roll"


def _fan_out(hub, logger) -> Callable[[dict], None]:
    """Print events to console and broadcast to hub if available."""
    def emit(event: dict) -> None:
        print(format_event(event))
        if hub is not None:
            hub.broadcast(event)

    return emit


def _harvest_on_confirm(logger, template_dir="templates/d20", max_per_face=6):
    from .keypoints import save_template

    def on_confirm(roll_id: str, value: int) -> None:
        logger.confirm(roll_id, value)
        path = logger.frame_path(roll_id)
        if not path.exists():
            return
        if len(list(Path(template_dir).glob(f"{value}_*.png"))) >= max_per_face:
            return
        frame = cv2.imread(str(path))
        if frame is not None:
            save_template(frame, value, template_dir)

    return on_confirm


def run_watch(
    frames: Iterator[np.ndarray],
    detector,
    chain,
    logger,
    emit: Callable[[dict], None],
    presence: Callable[[np.ndarray], bool] = _watch_gate,
) -> None:
    last_read: tuple[float, float, float] | None = None  # blob of the last reported die
    for frame in frames:
        result = detector.feed(frame)
        if result.state == SettleState.SETTLED:
            if not presence(result.frame):
                # hand retrieval / empty-tray motion: re-arm quietly, don't log;
                # the die has left, so the next settle anywhere is a new roll
                last_read = None
                detector.reset()
                continue
            ref = die_blob(result.frame)
            if ref is not None and _at_frame_edge(ref, result.frame):
                # clipped by the frame boundary = oblique view, unreadable in
                # principle; ask for a reroll like a cocked die
                emit({"type": "reroll", "reason": "tray-edge"})
                detector.reset()
                continue
            if ref is not None and last_read is not None and _die_unmoved(last_read, result.frame):
                # same die, same spot: a re-settle, not a roll
                detector.reset()
                continue
            candidates = [result.frame]
            if ref is not None:
                extra = list(itertools.islice(frames, POST_SETTLE_FRAMES))
                candidates += [f for f in extra if _die_unmoved(ref, f)]
            settled = max(candidates, key=sharpness)
            reading = chain.read(settled)
            rounds = 0
            while reading is None and ref is not None and rounds < RESAMPLE_ROUNDS:
                # resample: fresh frames, same die, retry every reader/crop
                rounds += 1
                extra = [f for f in itertools.islice(frames, POST_SETTLE_FRAMES) if _die_unmoved(ref, f)]
                if not extra:
                    break
                settled = max(extra, key=sharpness)
                reading = chain.read(settled)
            roll_id = logger.log(settled, reading)
            if reading is not None:
                emit({
                    "type": "result",
                    "roll_id": roll_id,
                    "value": reading.value,
                    "confidence": reading.confidence,
                    "reader": reading.reader,
                })
            else:
                emit({"type": "unread", "roll_id": roll_id})
            if ref is not None:
                last_read = ref
            detector.reset()
        elif result.state == SettleState.TIMEOUT:
            emit({"type": "timeout"})
            detector.reset()


def _build_chain() -> ReaderChain:
    readers = []
    from .keypoints import KeypointReader

    keypoints = KeypointReader()
    if keypoints.templates:
        readers.append(keypoints)
    if sys.platform == "darwin":
        from .readers.apple_vision import AppleVisionReader

        readers.append(AppleVisionReader())
    return ReaderChain(readers)


def _source_from_args(args):
    if args.video:
        return VideoFileSource(args.video)
    spec = args.camera
    if spec.isdigit():
        spec = int(spec)
    return CameraSource(spec)


def _zoom_frames(frames: Iterator[np.ndarray], factor: float) -> Iterator[np.ndarray]:
    """Digital zoom: center-crop each frame by factor (1.0 = no-op)."""
    for frame in frames:
        if factor <= 1.0:
            yield frame
            continue
        h, w = frame.shape[:2]
        ch, cw = int(h / factor), int(w / factor)
        y, x = (h - ch) // 2, (w - cw) // 2
        yield frame[y : y + ch, x : x + cw]


def _published_frames(frames: Iterator[np.ndarray], publisher) -> Iterator[np.ndarray]:
    """Tee every frame into the MJPEG publisher (rate-limited inside)."""
    for frame in frames:
        publisher.publish(frame)
        yield frame


def _preview_frames(frames: Iterator[np.ndarray]) -> Iterator[np.ndarray]:
    """Mirror the stream to an on-screen window; press 'q' there to stop."""
    try:
        for frame in frames:
            cv2.imshow("towereye watch", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            yield frame
    finally:
        cv2.destroyAllWindows()


PID_FILE = Path(".towereye-watch.pid")


def cmd_watch(args) -> int:
    PID_FILE.write_text(str(os.getpid()))
    try:
        return _cmd_watch(args)
    finally:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()


def _cmd_watch(args) -> int:
    from .camera_access import ensure_camera_access

    if not args.video and not ensure_camera_access():
        return 3
    chain = _build_chain()
    logger = RollLogger(args.log_dir)
    hub = None
    if not args.no_hub:
        from .hub import Hub

        try:
            hub = Hub(port=args.hub_port)
            hub.on_confirm = _harvest_on_confirm(logger)
            hub.start_in_thread()
            print(f"Hub listening on ws://127.0.0.1:{hub.port}")
        except Exception as exc:
            if "already in use" in str(exc).lower():
                print("Another watch already holds the hub port; not starting a duplicate.")
                return 2
            print(f"Hub unavailable ({exc}); continuing without it")
            hub = None
    stream = None
    if not args.no_stream:
        from .stream import FramePublisher, StreamServer

        try:
            stream = StreamServer(FramePublisher(), port=args.stream_port)
            stream.start_in_thread()
            print(f"Camera stream on http://127.0.0.1:{stream.port}/stream.mjpg")
        except OSError as exc:
            print(f"Stream unavailable ({exc}); continuing without it")
            stream = None
    print(f"Watching for rolls (log dir: {args.log_dir}). Ctrl-C to stop.")
    frames = _zoom_frames(_source_from_args(args).frames(), args.zoom)
    if stream is not None:
        frames = _published_frames(frames, stream.publisher)
    if args.preview:
        frames = _preview_frames(frames)
    try:
        run_watch(frames, SettleDetector(), chain, logger, _fan_out(hub, logger))
    except KeyboardInterrupt:
        pass
    finally:
        if hub is not None:
            hub.stop()
        if stream is not None:
            stream.stop()
    print("Session over.")
    return 0


def cmd_read(args) -> int:
    frame = cv2.imread(str(args.image))
    if frame is None:
        print(f"could not read image: {args.image}", file=sys.stderr)
        return 1
    reading = _build_chain().read(frame)
    if reading is None:
        print("no die value read")
        return 1
    print(f"{reading.value} ({reading.reader}, {reading.confidence:.2f})")
    return 0


def cmd_capture(args) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    print("Preview open: press 's' to save a frame, 'q' to quit.")
    for frame in _zoom_frames(_source_from_args(args).frames(), args.zoom):
        cv2.imshow("towereye capture", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            path = out_dir / f"capture-{saved:03d}.png"
            cv2.imwrite(str(path), frame)
            print(f"saved {path}")
            saved += 1
        elif key == ord("q"):
            break
    cv2.destroyAllWindows()
    return 0


def cmd_calibrate(args) -> int:
    from .keypoints import save_template

    faces = int(args.die.lower().lstrip("d"))
    out_dir = Path(args.out_dir) / args.die.lower()
    value = args.start
    print(
        "Calibration: place the die with the shown face UP, wait for focus, then\n"
        "press 's' to save a template (2-3 per face, nudge rotation between saves).\n"
        "'n' = next face, 'b' = previous face, 'q' = quit."
    )
    saved_this_face = 0
    for frame in _zoom_frames(_source_from_args(args).frames(), args.zoom):
        overlay = frame.copy()
        cv2.putText(
            overlay,
            f"{args.die} face {value}/{faces}  saved {saved_this_face}   s=save n=next b=back q=quit",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        cv2.imshow("towereye calibrate", overlay)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            path = save_template(frame, value, out_dir)
            if path is None:
                print("no die found in frame - check placement/lighting")
            else:
                saved_this_face += 1
                print(f"saved {path}")
        elif key == ord("n"):
            if value == faces:
                break
            value += 1
            saved_this_face = 0
        elif key == ord("b"):
            value = max(1, value - 1)
            saved_this_face = 0
        elif key == ord("q"):
            break
    cv2.destroyAllWindows()
    return 0


def probe_cameras(max_index: int = 6, warmup_seconds: float = 0.6, opener=cv2.VideoCapture) -> list[dict]:
    """Open each device index, let exposure settle, and return a thumbnail so
    a person can pick the camera by what it sees. Device order differs between
    AVFoundation, OpenCV, and the system camera list, so names can't be trusted."""
    import base64
    import time as _time

    from .camera_access import ensure_camera_access

    if not ensure_camera_access(log=lambda m: print(m, file=sys.stderr)):
        return []
    found = []
    for index in range(max_index):
        cap = opener(index)
        if not cap.isOpened():
            cap.release()
            continue
        frame = None
        deadline = _time.monotonic() + warmup_seconds
        while _time.monotonic() < deadline:
            ok, f = cap.read()
            if ok:
                frame = f
        cap.release()
        if frame is None:
            continue
        h, w = frame.shape[:2]
        thumb = cv2.resize(frame, (320, int(h * 320 / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
        found.append({
            "index": index,
            "width": w,
            "height": h,
            "thumbnail": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode() if ok else None,
        })
    return found


def cmd_cameras(args) -> int:
    import json

    cameras = probe_cameras(args.max_index)
    if args.json:
        print(json.dumps(cameras))
        return 0
    if not cameras:
        print("no cameras opened")
        return 1
    for cam in cameras:
        print(f"index {cam['index']}: {cam['width']}x{cam['height']}")
    return 0


def cmd_bench(args) -> int:
    from .bench import run_bench

    correct, total, mismatches = run_bench(args.golden_dir, _build_chain())
    for line in mismatches:
        print(f"MISS  {line}")
    if total == 0:
        print("no labeled golden frames found (expected names like 17_001.png)")
        return 1
    print(f"{correct}/{total} correct ({correct / total:.0%})")
    return 0


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Seed os.environ from a KEY=VALUE .env file; real environment wins."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if value.strip():
            os.environ.setdefault(key.strip(), value.strip())


def main(argv=None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(prog="towereye")
    sub = parser.add_subparsers(dest="command", required=True)

    watch = sub.add_parser("watch", help="watch the tray and read rolls")
    watch.add_argument("--camera", default="0", help="device index or stream URL")
    watch.add_argument("--video", help="video file instead of a live camera")
    watch.add_argument("--log-dir", default="dataset", help="roll dataset directory")
    watch.add_argument("--zoom", type=float, default=1.0, help="digital zoom factor (center crop, 1.0 = full field)")
    watch.add_argument("--preview", action="store_true", help="show the live feed in a window")
    watch.add_argument("--hub-port", type=int, default=8777, help="WebSocket hub port")
    watch.add_argument("--no-hub", action="store_true", help="disable the WebSocket hub")
    watch.add_argument("--stream-port", type=int, default=8778, help="MJPEG camera stream port (for the OBS overlay)")
    watch.add_argument("--no-stream", action="store_true", help="disable the camera stream")
    watch.set_defaults(func=cmd_watch)

    read = sub.add_parser("read", help="read a die from a still image")
    read.add_argument("image")
    read.set_defaults(func=cmd_read)

    capture = sub.add_parser("capture", help="preview the camera and save frames")
    capture.add_argument("--camera", default="0", help="device index or stream URL")
    capture.add_argument("--video", help=argparse.SUPPRESS)
    capture.add_argument("--out-dir", default="captures")
    capture.add_argument("--zoom", type=float, default=1.5, help="digital zoom factor (center crop, 1.0 = full field)")
    capture.set_defaults(func=cmd_capture)

    cameras = sub.add_parser("cameras", help="list openable camera indices (with thumbnails in --json)")
    cameras.add_argument("--json", action="store_true", help="machine-readable output incl. thumbnails")
    cameras.add_argument("--max-index", type=int, default=6)
    cameras.set_defaults(func=cmd_cameras)

    bench = sub.add_parser("bench", help="score readers against labeled golden frames")
    bench.add_argument("golden_dir")
    bench.set_defaults(func=cmd_bench)

    calibrate = sub.add_parser("calibrate", help="capture per-face keypoint templates")
    calibrate.add_argument("--camera", default="0", help="device index or stream URL")
    calibrate.add_argument("--video", help=argparse.SUPPRESS)
    calibrate.add_argument("--zoom", type=float, default=1.5, help="digital zoom factor (center crop, 1.0 = full field)")
    calibrate.add_argument("--out-dir", default="templates", help="template root; die pools live in <out-dir>/<die>/")
    calibrate.add_argument("--die", default="d20", help="which die: d20, d8, d12 ... sets the face count and pool")
    calibrate.add_argument("--start", type=int, default=1, help="face value to start from")
    calibrate.set_defaults(func=cmd_calibrate)

    args = parser.parse_args(argv)
    return args.func(args)
