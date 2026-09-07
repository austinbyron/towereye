# towereye M1 (Proof of Read) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI that watches the dice tower tray through a camera, detects when a single die has settled, reads the top-face number via a reader chain (Apple Vision OCR → Claude Haiku vision), prints "You rolled 17", and logs every roll as a future training sample.

**Architecture:** A `FrameSource` abstraction feeds frames to a `SettleDetector` state machine (classical OpenCV motion diff). When a die settles, the settled frame goes through a `ReaderChain` of pluggable `Reader`s. Every roll is logged (frame PNG + JSONL row) by `RollLogger`. A thin CLI wires these together; `capture` and `read` subcommands help aim the rig and debug readers on stills.

**Tech Stack:** Python 3.12 venv, opencv-python, numpy, pyobjc (Vision framework), anthropic SDK (Haiku vision), pytest, Pillow (tests only). No torch anywhere.

## Global Constraints

- Repo: `~/CodeProjects/towereye` (already exists, git initialized on `master`, contains `docs/` only).
- Python: create venv with `python3.12` (system python3.13 not required; torch is irrelevant — never add it).
- Haiku model id: exactly `claude-haiku-4-5`. Auth via `ANTHROPIC_API_KEY` env var (standard SDK resolution).
- Die values are integers 1–20; a reading outside that range is invalid.
- Commit messages: plain text only. A **global git hook rejects** any `Co-Authored-By`, robot emoji, or "Generated with Claude" lines — never add them.
- macOS-only code (pyobjc Vision) must be import-guarded and its tests skipped off-darwin (`pytest.mark.skipif(sys.platform != "darwin", ...)`).
- All commands below run from the repo root with the venv activated (`source .venv/bin/activate`).

---

### Task 1: Scaffold + frame sources

**Files:**
- Create: `requirements.txt`, `.gitignore`, `towereye/__init__.py`, `towereye/frames.py`
- Test: `tests/test_frames.py`

**Interfaces:**
- Produces: `FrameSource` protocol with `frames() -> Iterator[np.ndarray]` (BGR uint8 frames); `VideoFileSource(path)`; `CameraSource(spec)` where `spec` is an `int` device index or `str` URL. Later tasks consume `frames()` only.

- [ ] **Step 1: Create venv and requirements**

`requirements.txt`:
```
opencv-python>=4.9
numpy>=1.26
anthropic>=0.40
pyobjc-framework-Vision>=10.0; sys_platform == "darwin"
pyobjc-framework-Quartz>=10.0; sys_platform == "darwin"
pytest>=8.0
Pillow>=10.0
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
dataset/
.pytest_cache/
```

Run:
```bash
cd ~/CodeProjects/towereye
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Expected: install succeeds (pyobjc lines install on macOS).

- [ ] **Step 2: Write the failing test**

`tests/test_frames.py`:
```python
import cv2
import numpy as np

from towereye.frames import VideoFileSource


def _write_video(path, n_frames=10, size=(64, 48)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, size)
    for i in range(n_frames):
        frame = np.full((size[1], size[0], 3), i * 10, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_video_file_source_yields_all_frames(tmp_path):
    video = tmp_path / "clip.mp4"
    _write_video(video, n_frames=10)
    frames = list(VideoFileSource(video).frames())
    assert len(frames) == 10
    assert frames[0].shape == (48, 64, 3)
    assert frames[0].dtype == np.uint8
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_frames.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'towereye'` (or ImportError for `frames`).

- [ ] **Step 4: Write minimal implementation**

`towereye/__init__.py`: empty file.

`towereye/frames.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_frames.py -v`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore towereye/ tests/
git commit -m "Add project scaffold and frame sources"
```

---

### Task 2: Settle detector

**Files:**
- Create: `towereye/settle.py`
- Test: `tests/test_settle.py`

**Interfaces:**
- Consumes: BGR frames (np.ndarray) from any `FrameSource`.
- Produces: `SettleState` enum (`WAITING`, `MOTION`, `SETTLED`, `TIMEOUT`); `SettleResult(state, frame)` dataclass; `SettleDetector(motion_threshold=4.0, settle_frames=15, timeout_frames=300)` with `feed(frame) -> SettleResult` and `reset() -> None`. `SETTLED` fires exactly once per throw and carries the settled frame; caller must `reset()` before the next throw.

- [ ] **Step 1: Write the failing tests**

`tests/test_settle.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settle.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` on `towereye.settle`.

- [ ] **Step 3: Write the implementation**

`towereye/settle.py`:
```python
"""Motion-based settle detection: fire once when a thrown die comes to rest."""
from dataclasses import dataclass
from enum import Enum, auto

import cv2
import numpy as np


class SettleState(Enum):
    WAITING = auto()   # no motion observed yet (empty tray / idle)
    MOTION = auto()    # die currently moving
    SETTLED = auto()   # motion stopped after motion — frame attached
    TIMEOUT = auto()   # motion never stopped within timeout_frames
    DONE = auto()      # already settled/timed out; reset() to re-arm


@dataclass
class SettleResult:
    state: SettleState
    frame: np.ndarray | None = None


class SettleDetector:
    def __init__(
        self,
        motion_threshold: float = 4.0,
        settle_frames: int = 15,
        timeout_frames: int = 300,
    ):
        self.motion_threshold = motion_threshold
        self.settle_frames = settle_frames
        self.timeout_frames = timeout_frames
        self.reset()

    def reset(self) -> None:
        self._prev: np.ndarray | None = None
        self._motion_seen = False
        self._still_count = 0
        self._frames_since_motion = 0
        self._done = False

    def _prep(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def feed(self, frame: np.ndarray) -> SettleResult:
        if self._done:
            return SettleResult(SettleState.DONE)
        cur = self._prep(frame)
        if self._prev is None:
            self._prev = cur
            return SettleResult(SettleState.WAITING)
        diff = float(np.mean(cv2.absdiff(cur, self._prev)))
        self._prev = cur

        if not self._motion_seen:
            if diff > self.motion_threshold:
                self._motion_seen = True
                self._frames_since_motion = 0
                return SettleResult(SettleState.MOTION)
            return SettleResult(SettleState.WAITING)

        self._frames_since_motion += 1
        if self._frames_since_motion > self.timeout_frames:
            self._done = True
            return SettleResult(SettleState.TIMEOUT)

        if diff > self.motion_threshold:
            self._still_count = 0
            return SettleResult(SettleState.MOTION)

        self._still_count += 1
        if self._still_count >= self.settle_frames:
            self._done = True
            return SettleResult(SettleState.SETTLED, frame=frame)
        return SettleResult(SettleState.MOTION)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settle.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add towereye/settle.py tests/test_settle.py
git commit -m "Add motion-based settle detector"
```

---

### Task 3: Reading type, value parsing, and reader chain

**Files:**
- Create: `towereye/readers/__init__.py`
- Test: `tests/test_chain.py`

**Interfaces:**
- Produces: `Reading(value: int, confidence: float, reader: str)` dataclass; `parse_die_value(text: str) -> int | None`; `Reader` protocol with attribute `name: str` and method `read(frame: np.ndarray) -> Reading | None`; `ReaderChain(readers: list, min_confidence: float = 0.5)` with `read(frame) -> Reading | None`. Chain semantics: return the first reading with `confidence >= min_confidence`; if none qualifies, return the highest-confidence reading found (or None).

- [ ] **Step 1: Write the failing tests**

`tests/test_chain.py`:
```python
import numpy as np

from towereye.readers import Reading, ReaderChain, parse_die_value

FRAME = np.zeros((10, 10, 3), dtype=np.uint8)


class FakeReader:
    def __init__(self, name, reading):
        self.name = name
        self._reading = reading
        self.called = False

    def read(self, frame):
        self.called = True
        return self._reading


def test_parse_die_value():
    assert parse_die_value("17") == 17
    assert parse_die_value(" 6.\n") == 6   # underline/dot marks on d20 faces
    assert parse_die_value("9_") == 9
    assert parse_die_value("21") is None   # out of range
    assert parse_die_value("0") is None
    assert parse_die_value("banana") is None
    assert parse_die_value("") is None


def test_chain_returns_first_confident_reading():
    first = FakeReader("a", Reading(value=17, confidence=0.9, reader="a"))
    second = FakeReader("b", Reading(value=3, confidence=0.99, reader="b"))
    chain = ReaderChain([first, second], min_confidence=0.5)
    result = chain.read(FRAME)
    assert result.value == 17 and result.reader == "a"
    assert not second.called  # cheap reader short-circuits the chain


def test_chain_falls_through_on_low_confidence():
    weak = FakeReader("a", Reading(value=6, confidence=0.2, reader="a"))
    strong = FakeReader("b", Reading(value=9, confidence=0.9, reader="b"))
    chain = ReaderChain([weak, strong], min_confidence=0.5)
    assert chain.read(FRAME).value == 9


def test_chain_returns_best_effort_when_all_weak():
    weak1 = FakeReader("a", Reading(value=6, confidence=0.2, reader="a"))
    weak2 = FakeReader("b", Reading(value=9, confidence=0.4, reader="b"))
    chain = ReaderChain([weak1, weak2], min_confidence=0.5)
    result = chain.read(FRAME)
    assert result.value == 9 and result.confidence == 0.4


def test_chain_returns_none_when_all_fail():
    chain = ReaderChain([FakeReader("a", None), FakeReader("b", None)])
    assert chain.read(FRAME) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chain.py -v`
Expected: FAIL with ImportError on `towereye.readers`.

- [ ] **Step 3: Write the implementation**

`towereye/readers/__init__.py`:
```python
"""Reader protocol, value parsing, and the cheapest-first reader chain."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Reading:
    value: int
    confidence: float
    reader: str


class Reader(Protocol):
    name: str

    def read(self, frame: np.ndarray) -> Reading | None: ...


def parse_die_value(text: str) -> int | None:
    """Parse OCR/LLM output into a die value 1-20, tolerating 6./9_ marks."""
    cleaned = text.strip().strip("._,")
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    return value if 1 <= value <= 20 else None


class ReaderChain:
    def __init__(self, readers: list[Reader], min_confidence: float = 0.5):
        self.readers = readers
        self.min_confidence = min_confidence

    def read(self, frame: np.ndarray) -> Reading | None:
        best: Reading | None = None
        for reader in self.readers:
            reading = reader.read(frame)
            if reading is None:
                continue
            if reading.confidence >= self.min_confidence:
                return reading
            if best is None or reading.confidence > best.confidence:
                best = reading
        return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chain.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add towereye/readers/ tests/test_chain.py
git commit -m "Add reading type, die value parsing, and reader chain"
```

---

### Task 4: Apple Vision OCR reader

**Files:**
- Create: `towereye/readers/apple_vision.py`
- Test: `tests/test_apple_vision.py`

**Interfaces:**
- Consumes: `Reading`, `parse_die_value` from `towereye.readers`.
- Produces: `AppleVisionReader` with `name = "apple_vision"` and `read(frame) -> Reading | None`. macOS-only; instantiating on non-darwin raises `RuntimeError`.

- [ ] **Step 1: Write the failing tests**

`tests/test_apple_vision.py`:
```python
import sys

import numpy as np
import pytest

darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="Vision framework is macOS-only")


def _digit_frame(text: str, size=200):
    """White frame with large black digits, rendered via PIL."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except OSError:
        font = ImageFont.load_default(size=120)
    draw.text((size // 2, size // 2), text, fill="black", font=font, anchor="mm")
    rgb = np.array(img)
    return rgb[:, :, ::-1].copy()  # RGB -> BGR


@darwin_only
def test_reads_two_digit_number():
    from towereye.readers.apple_vision import AppleVisionReader

    reading = AppleVisionReader().read(_digit_frame("17"))
    assert reading is not None
    assert reading.value == 17
    assert reading.reader == "apple_vision"
    assert 0.0 < reading.confidence <= 1.0


@darwin_only
def test_blank_frame_returns_none():
    from towereye.readers.apple_vision import AppleVisionReader

    blank = np.full((200, 200, 3), 255, dtype=np.uint8)
    assert AppleVisionReader().read(blank) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_apple_vision.py -v`
Expected: FAIL with ImportError on `towereye.readers.apple_vision` (on macOS; skipped elsewhere).

- [ ] **Step 3: Write the implementation**

`towereye/readers/apple_vision.py`:
```python
"""Free local OCR via the macOS Vision framework (VNRecognizeTextRequest)."""
import sys

import cv2
import numpy as np

from . import Reading, parse_die_value


class AppleVisionReader:
    name = "apple_vision"

    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("AppleVisionReader requires macOS")
        import Vision  # noqa: F401 - fail fast if pyobjc-framework-Vision is missing

    def read(self, frame: np.ndarray) -> Reading | None:
        import Vision
        from Foundation import NSData

        ok, png = cv2.imencode(".png", frame)
        if not ok:
            return None
        data = NSData.dataWithBytes_length_(png.tobytes(), len(png))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(False)
        success = handler.performRequests_error_([request], None)
        # pyobjc returns (bool, error) for out-params on some versions, bool on others
        if isinstance(success, tuple):
            success = success[0]
        if not success:
            return None

        best: Reading | None = None
        for observation in request.results() or []:
            for candidate in observation.topCandidates_(1):
                value = parse_die_value(str(candidate.string()))
                if value is None:
                    continue
                confidence = float(candidate.confidence())
                if best is None or confidence > best.confidence:
                    best = Reading(value=value, confidence=confidence, reader=self.name)
        return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_apple_vision.py -v`
Expected: PASS (2 tests) on macOS. If `test_reads_two_digit_number` fails because Vision returns nothing, debug interactively (`python -c` with the same code path on the rendered image) — the pyobjc out-param convention (step 3 comment) is the usual culprit.

- [ ] **Step 5: Commit**

```bash
git add towereye/readers/apple_vision.py tests/test_apple_vision.py
git commit -m "Add Apple Vision OCR reader"
```

---

### Task 5: Haiku vision reader

**Files:**
- Create: `towereye/readers/haiku.py`
- Test: `tests/test_haiku.py`

**Interfaces:**
- Consumes: `Reading`, `parse_die_value` from `towereye.readers`.
- Produces: `HaikuReader(client=None)` with `name = "haiku"`, `calls: int` counter (per-session cost display), and `read(frame) -> Reading | None`. API errors return None (chain degrades gracefully). Model id `claude-haiku-4-5`.

- [ ] **Step 1: Write the failing tests**

`tests/test_haiku.py`:
```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import numpy as np

from towereye.readers.haiku import HaikuReader

FRAME = np.zeros((100, 100, 3), dtype=np.uint8)


def _mock_client(reply_text):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=reply_text)]
    )
    return client


def test_parses_reply_into_reading():
    client = _mock_client("17")
    reader = HaikuReader(client=client)
    reading = reader.read(FRAME)
    assert reading.value == 17
    assert reading.reader == "haiku"
    assert reader.calls == 1
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    image_block = kwargs["messages"][0]["content"][0]
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"


def test_garbage_reply_returns_none():
    reader = HaikuReader(client=_mock_client("I cannot tell"))
    assert reader.read(FRAME) is None


def test_api_error_returns_none():
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com")
    )
    reader = HaikuReader(client=client)
    assert reader.read(FRAME) is None
    assert reader.calls == 1  # failed calls still count toward the session counter
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_haiku.py -v`
Expected: FAIL with ImportError on `towereye.readers.haiku`.

- [ ] **Step 3: Write the implementation**

`towereye/readers/haiku.py`:
```python
"""Cloud fallback reader: one Claude Haiku vision call per settled roll."""
import base64

import anthropic
import cv2
import numpy as np

from . import Reading, parse_die_value

PROMPT = (
    "This photo shows a single die resting in a dice tray. "
    "Reply with only the integer shown on its top face, nothing else."
)


class HaikuReader:
    name = "haiku"
    MODEL = "claude-haiku-4-5"

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()
        self.calls = 0

    def read(self, frame: np.ndarray) -> Reading | None:
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        data = base64.standard_b64encode(jpg.tobytes()).decode("utf-8")
        self.calls += 1
        try:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=16,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": data,
                            },
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }],
            )
        except anthropic.APIError:
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        value = parse_die_value(text)
        if value is None:
            return None
        # Haiku gives no confidence score; a parseable in-range answer is trusted.
        return Reading(value=value, confidence=0.9, reader=self.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_haiku.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add towereye/readers/haiku.py tests/test_haiku.py
git commit -m "Add Claude Haiku vision reader"
```

---

### Task 6: Roll logger (the future training set)

**Files:**
- Create: `towereye/datalog.py`
- Test: `tests/test_datalog.py`

**Interfaces:**
- Consumes: `Reading` from `towereye.readers`.
- Produces: `RollLogger(root: Path)` with `log(frame, reading, context=None) -> str` (returns roll id). Writes `root/frames/<roll_id>.png` and appends a JSON line to `root/rolls.jsonl` with keys `id, predicted, confidence, reader, context, confirmed` (`confirmed` is always `null` in M1; M2's companion fills it in).

- [ ] **Step 1: Write the failing tests**

`tests/test_datalog.py`:
```python
import json

import numpy as np

from towereye.datalog import RollLogger
from towereye.readers import Reading

FRAME = np.zeros((20, 20, 3), dtype=np.uint8)


def test_logs_frame_and_row(tmp_path):
    logger = RollLogger(tmp_path / "dataset")
    reading = Reading(value=17, confidence=0.9, reader="haiku")
    roll_id = logger.log(FRAME, reading, context="Initiative")

    assert (tmp_path / "dataset" / "frames" / f"{roll_id}.png").exists()
    rows = [json.loads(l) for l in (tmp_path / "dataset" / "rolls.jsonl").read_text().splitlines()]
    assert rows == [{
        "id": roll_id,
        "predicted": 17,
        "confidence": 0.9,
        "reader": "haiku",
        "context": "Initiative",
        "confirmed": None,
    }]


def test_logs_failed_reading(tmp_path):
    logger = RollLogger(tmp_path / "dataset")
    roll_id = logger.log(FRAME, None)
    row = json.loads((tmp_path / "dataset" / "rolls.jsonl").read_text())
    assert row["id"] == roll_id
    assert row["predicted"] is None and row["reader"] is None


def test_ids_are_unique_within_a_second(tmp_path):
    logger = RollLogger(tmp_path / "dataset")
    ids = {logger.log(FRAME, None) for _ in range(3)}
    assert len(ids) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_datalog.py -v`
Expected: FAIL with ImportError on `towereye.datalog`.

- [ ] **Step 3: Write the implementation**

`towereye/datalog.py`:
```python
"""Persist every roll (frame + prediction) as a labeled-training-data candidate."""
import json
import time
from itertools import count
from pathlib import Path

import cv2
import numpy as np

from .readers import Reading


class RollLogger:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.frames_dir = self.root / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.rows_path = self.root / "rolls.jsonl"
        self._seq = count()

    def log(self, frame: np.ndarray, reading: Reading | None, context: str | None = None) -> str:
        roll_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{next(self._seq):03d}"
        cv2.imwrite(str(self.frames_dir / f"{roll_id}.png"), frame)
        row = {
            "id": roll_id,
            "predicted": reading.value if reading else None,
            "confidence": reading.confidence if reading else None,
            "reader": reading.reader if reading else None,
            "context": context,
            "confirmed": None,
        }
        with self.rows_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return roll_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_datalog.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add towereye/datalog.py tests/test_datalog.py
git commit -m "Add roll logger for dataset accumulation"
```

---

### Task 7: CLI — watch, read, capture

**Files:**
- Create: `towereye/cli.py`, `towereye/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `run_watch(frames, detector, chain, logger, report) -> None` (testable core loop; `report` is a callable taking a string). CLI entry points:
  - `python -m towereye watch --camera 0` or `--camera <url>` or `--video clip.mp4` (`--log-dir dataset` default)
  - `python -m towereye read image.png` — run the reader chain on a still, print the result
  - `python -m towereye capture --camera 0` — live preview window; press `s` to save a frame into `captures/`, `q` to quit (for aiming the rig and collecting golden frames)

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import numpy as np

from towereye.cli import run_watch
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

    def log(self, frame, reading, context=None):
        self.entries.append(reading)
        return "test-id"


def _throw_frames():
    def square(x):
        f = np.zeros((48, 64, 3), dtype=np.uint8)
        f[10:30, x : x + 20] = 255
        return f

    return [square(x) for x in range(0, 30, 6)] + [square(24)] * 10


def test_run_watch_reports_and_logs_settled_roll():
    lines = []
    logger = ListLogger()
    run_watch(
        frames=iter(_throw_frames()),
        detector=SettleDetector(settle_frames=3, timeout_frames=100),
        chain=FixedReader(7),
        logger=logger,
        report=lines.append,
    )
    assert any("You rolled 7" in line for line in lines)
    assert len(logger.entries) == 1
    assert logger.entries[0].value == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with ImportError on `towereye.cli`.

- [ ] **Step 3: Write the implementation**

`towereye/cli.py`:
```python
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

    args = parser.parse_args(argv)
    return args.func(args)
```

`towereye/__main__.py`:
```python
import sys

from .cli import main

sys.exit(main())
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: ALL tests pass (frames, settle, chain, apple_vision, haiku, datalog, cli).

- [ ] **Step 5: Commit**

```bash
git add towereye/cli.py towereye/__main__.py tests/test_cli.py
git commit -m "Add watch/read/capture CLI"
```

---

### Task 8: Golden-set benchmark command

**Files:**
- Modify: `towereye/cli.py` (add `bench` subcommand)
- Create: `towereye/bench.py`
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: `ReaderChain` protocol (anything with `read(frame)`).
- Produces: `parse_golden_name(path) -> int | None` (filename convention `<label>_<anything>.png`, e.g. `17_003.png` → 17); `run_bench(golden_dir, chain) -> tuple[int, int, list[str]]` returning (correct, total, mismatch descriptions). CLI: `python -m towereye bench golden/`.

- [ ] **Step 1: Write the failing tests**

`tests/test_bench.py`:
```python
import cv2
import numpy as np

from towereye.bench import parse_golden_name, run_bench
from towereye.readers import Reading


class FixedReader:
    def __init__(self, value):
        self._value = value

    def read(self, frame):
        if self._value is None:
            return None
        return Reading(value=self._value, confidence=1.0, reader="fixed")


def test_parse_golden_name():
    from pathlib import Path

    assert parse_golden_name(Path("17_003.png")) == 17
    assert parse_golden_name(Path("6_a.png")) == 6
    assert parse_golden_name(Path("notes.png")) is None


def test_run_bench_scores_against_labels(tmp_path):
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "17_001.png"), frame)
    cv2.imwrite(str(tmp_path / "3_001.png"), frame)
    correct, total, mismatches = run_bench(tmp_path, FixedReader(17))
    assert (correct, total) == (1, 2)
    assert len(mismatches) == 1 and "3_001" in mismatches[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bench.py -v`
Expected: FAIL with ImportError on `towereye.bench`.

- [ ] **Step 3: Write the implementation**

`towereye/bench.py`:
```python
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
```

Add to `towereye/cli.py` (a new command function plus subparser registration inside `main`):
```python
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
```
and inside `main()` after the `capture` subparser:
```python
    bench = sub.add_parser("bench", help="score readers against labeled golden frames")
    bench.add_argument("golden_dir")
    bench.set_defaults(func=cmd_bench)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass.

- [ ] **Step 5: Commit**

```bash
git add towereye/bench.py towereye/cli.py tests/test_bench.py
git commit -m "Add golden-set benchmark command"
```

---

### Task 9: Live rig verification (manual, with Austin)

No new code. This is the M1 exit criterion and needs the physical rig.

- [ ] **Step 1: Camera hookup.** Mount the iPhone over the tray (Continuity Camera if it appears as a device; otherwise an IP-camera app and use its MJPEG/RTSP URL as `--camera <url>`). Clip the LED light on. Run `python -m towereye capture --camera 0` (try indices 0/1/2 to find the iPhone) and adjust framing until the tray fills most of the frame in focus.
- [ ] **Step 2: Save golden frames.** Roll each die a few times; press `s` on settled frames. Rename saved files to `<value>_<n>.png` and move them into `golden/`.
- [ ] **Step 3: Benchmark.** Run `python -m towereye bench golden/`. Record the score — this is the baseline that phase 2's local model must beat. If Apple Vision misses badly, that's expected on some faces; the Haiku fallback should carry it. Requires `ANTHROPIC_API_KEY` in the environment.
- [ ] **Step 4: Live watch.** Run `python -m towereye watch --camera <spec>`, drop dice, confirm "You rolled N" prints correctly and `dataset/` accumulates frames + rows. Tune `SettleDetector` thresholds via real behavior if it fires early/late (a follow-up commit adjusting defaults is expected).
- [ ] **Step 5: Commit any tuning**

```bash
git add -A
git commit -m "Tune settle detection thresholds from live rig testing"
```

**M1 is done when:** a real physical roll prints the correct number in the terminal and lands in `dataset/`, with Haiku call count reported at session end.
