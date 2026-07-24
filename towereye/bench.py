"""Score the reader chain against a directory of labeled golden frames."""
from pathlib import Path

import cv2


def parse_golden_name(path: Path) -> int | None:
    """Golden frames are named '<label>_<anything>.png', e.g. 17_003.png."""
    head = path.stem.split("_", 1)[0]
    if not head.isdigit():
        return None
    value = int(head)
    return value if 1 <= value <= 20 else None


def run_bench(golden_dir: str | Path, chain) -> tuple[int, int, list[str]]:
    correct, total, mismatches = 0, 0, []
    for path in sorted(Path(golden_dir).glob("*.png")):
        label = parse_golden_name(path)
        if label is None:
            continue
        frame = cv2.imread(str(path))
        if frame is None:
            continue
        total += 1
        reading = chain.read(frame)
        got = reading.value if reading else None
        if got == label:
            correct += 1
        else:
            mismatches.append(f"{path.name}: expected {label}, got {got}")
    return correct, total, mismatches
