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
from .presence import CENTER_CROP, die_present
from .readers import ReaderChain
from .settle import SettleDetector, SettleState
from .topface import die_blob, sharpness

# frames to pull after a settle so autofocus can catch up (~0.5s at 30fps);
# the sharpest STABLE one is read
POST_SETTLE_FRAMES = 15


def _die_unmoved(ref: tuple[float, float, float], frame: np.ndarray) -> bool:
    """True if the frame's die blob matches the settle frame's position/size —
    guards against reading a frame where the hand already lifted the die."""
    blob = die_blob(frame)
    if blob is None:
        return False
    (rx, ry, rr), (cx, cy, cr) = ref, blob
    return abs(cx - rx) <= 0.5 * rr and abs(cy - ry) <= 0.5 * rr and 0.7 <= cr / rr <= 1.4


def run_watch(
    frames: Iterator[np.ndarray],
    detector,
    chain,
    logger,
    report: Callable[[str], None],
    presence: Callable[[np.ndarray], bool] = die_present,
) -> None:
    for frame in frames:
        result = detector.feed(frame)
        if result.state == SettleState.SETTLED:
            if not presence(result.frame):
                # hand retrieval / empty-tray motion: re-arm quietly, don't log
                detector.reset()
                continue
            ref = die_blob(result.frame)
            candidates = [result.frame]
            if ref is not None:
                extra = itertools.islice(frames, POST_SETTLE_FRAMES)
                candidates += [f for f in extra if _die_unmoved(ref, f)]
            settled = max(candidates, key=sharpness)
            reading = chain.read(settled)
            if reading is not None:
                report(f"You rolled {reading.value} ({reading.reader}, {reading.confidence:.2f})")
            else:
                report("Could not read the die - check lighting/framing")
            logger.log(settled, reading)
            detector.reset()
        elif result.state == SettleState.TIMEOUT:
            report("Die never settled (cocked or bounced out?) - re-roll")
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
    from .readers.haiku import HaikuReader

    haiku = HaikuReader()
    readers.append(haiku)
    chain = ReaderChain(readers)
    chain.haiku = haiku  # expose for the session call counter
    return chain


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


def cmd_watch(args) -> int:
    chain = _build_chain()
    logger = RollLogger(args.log_dir)
    print(f"Watching for rolls (log dir: {args.log_dir}). Ctrl-C to stop.")
    frames = _zoom_frames(_source_from_args(args).frames(), args.zoom)
    if args.preview:
        frames = _preview_frames(frames)
    # zoom pre-crops the frame, so widen the gate's crop to keep watching
    # the same physical tray region it was tuned on
    gate_crop = min(1.0, CENTER_CROP * max(args.zoom, 1.0))
    try:
        run_watch(
            frames,
            SettleDetector(),
            chain,
            logger,
            print,
            presence=lambda f: die_present(f, center_crop=gate_crop),
        )
    except KeyboardInterrupt:
        pass
    print(f"Session over. Haiku API calls this session: {chain.haiku.calls}")
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

    out_dir = Path(args.out_dir)
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
            f"face {value}/20  saved {saved_this_face}   s=save n=next b=back q=quit",
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
            if value == 20:
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
    watch.add_argument("--zoom", type=float, default=1.5, help="digital zoom factor (center crop)")
    watch.add_argument("--preview", action="store_true", help="show the live feed in a window")
    watch.set_defaults(func=cmd_watch)

    read = sub.add_parser("read", help="read a die from a still image")
    read.add_argument("image")
    read.set_defaults(func=cmd_read)

    capture = sub.add_parser("capture", help="preview the camera and save frames")
    capture.add_argument("--camera", default="0", help="device index or stream URL")
    capture.add_argument("--video", help=argparse.SUPPRESS)
    capture.add_argument("--out-dir", default="captures")
    capture.add_argument("--zoom", type=float, default=1.5, help="digital zoom factor (center crop)")
    capture.set_defaults(func=cmd_capture)

    bench = sub.add_parser("bench", help="score readers against labeled golden frames")
    bench.add_argument("golden_dir")
    bench.set_defaults(func=cmd_bench)

    calibrate = sub.add_parser("calibrate", help="capture per-face keypoint templates")
    calibrate.add_argument("--camera", default="0", help="device index or stream URL")
    calibrate.add_argument("--video", help=argparse.SUPPRESS)
    calibrate.add_argument("--zoom", type=float, default=1.5, help="digital zoom factor (center crop)")
    calibrate.add_argument("--out-dir", default="templates")
    calibrate.add_argument("--start", type=int, default=1, help="face value to start from")
    calibrate.set_defaults(func=cmd_calibrate)

    args = parser.parse_args(argv)
    return args.func(args)
