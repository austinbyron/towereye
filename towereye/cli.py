"""towereye CLI: watch the tray, read stills, capture frames for the golden set."""
import argparse
import sys
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from .datalog import RollLogger
from .frames import CameraSource, VideoFileSource
from .readers import ReaderChain
from .settle import SettleDetector, SettleState


def run_watch(frames: Iterator[np.ndarray], detector, chain, logger, report: Callable[[str], None]) -> None:
    for frame in frames:
        result = detector.feed(frame)
        if result.state == SettleState.SETTLED:
            reading = chain.read(result.frame)
            if reading is not None:
                report(f"You rolled {reading.value} ({reading.reader}, {reading.confidence:.2f})")
            else:
                report("Could not read the die - check lighting/framing")
            logger.log(result.frame, reading)
            detector.reset()
        elif result.state == SettleState.TIMEOUT:
            report("Die never settled (cocked or bounced out?) - re-roll")
            detector.reset()


def _build_chain() -> ReaderChain:
    readers = []
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


def cmd_watch(args) -> int:
    chain = _build_chain()
    logger = RollLogger(args.log_dir)
    print(f"Watching for rolls (log dir: {args.log_dir}). Ctrl-C to stop.")
    try:
        run_watch(_source_from_args(args).frames(), SettleDetector(), chain, logger, print)
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
    for frame in _source_from_args(args).frames():
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="towereye")
    sub = parser.add_subparsers(dest="command", required=True)

    watch = sub.add_parser("watch", help="watch the tray and read rolls")
    watch.add_argument("--camera", default="0", help="device index or stream URL")
    watch.add_argument("--video", help="video file instead of a live camera")
    watch.add_argument("--log-dir", default="dataset", help="roll dataset directory")
    watch.set_defaults(func=cmd_watch)

    read = sub.add_parser("read", help="read a die from a still image")
    read.add_argument("image")
    read.set_defaults(func=cmd_read)

    capture = sub.add_parser("capture", help="preview the camera and save frames")
    capture.add_argument("--camera", default="0", help="device index or stream URL")
    capture.add_argument("--video", help=argparse.SUPPRESS)
    capture.add_argument("--out-dir", default="captures")
    capture.set_defaults(func=cmd_capture)

    bench = sub.add_parser("bench", help="score readers against labeled golden frames")
    bench.add_argument("golden_dir")
    bench.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    return args.func(args)
