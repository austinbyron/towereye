"""Free local OCR via the macOS Vision framework (VNRecognizeTextRequest)."""
import sys

import cv2
import numpy as np

from . import Reading, parse_die_value

ROTATIONS = 8        # Vision can't read rotated text; sweep the crop through 45° steps
MAX_CENTER_DIST = 0.30  # normalized; numerals further from center are side faces
MIN_CONFIDENCE = 0.3
CONFLICT_DIST_MARGIN = 0.07  # rival value this close to center = ambiguous read
CONFLICT_CONFIDENCE = 0.45   # below the chain gate, so the next reader arbitrates


def _select(candidates, reader_name: str) -> Reading | None:
    """Pick the top face: nearest numeral to the crop center, not the crispest.

    candidates: (value, confidence, normalized distance from image center).
    Off-axis rotations can degrade glyphs (17 -> 11), so when two values
    compete at similar centrality the read is demoted below the chain gate.
    """
    kept = [c for c in candidates if c[1] >= MIN_CONFIDENCE and c[2] <= MAX_CENTER_DIST]
    if not kept:
        return None
    value, confidence, dist = min(kept, key=lambda c: (round(c[2], 2), -c[1]))
    rival = any(c[0] != value and c[2] <= dist + CONFLICT_DIST_MARGIN for c in kept)
    # split-teen check: an off-center crop can separate a teen's leading 1 from
    # its second digit (17 read as 7); a 10+d sighting anywhere casts doubt on d
    teen = value <= 9 and any(
        c[0] == value + 10 and c[1] >= MIN_CONFIDENCE for c in candidates
    )
    if rival or teen:
        confidence = min(confidence, CONFLICT_CONFIDENCE)
    return Reading(value=value, confidence=confidence, reader=reader_name)


class AppleVisionReader:
    name = "apple_vision"

    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("AppleVisionReader requires macOS")
        import Vision  # noqa: F401 - fail fast if pyobjc-framework-Vision is missing

    def _ocr(self, frame: np.ndarray) -> list[tuple[int, float, float]]:
        import Vision
        from Foundation import NSData

        ok, png = cv2.imencode(".png", frame)
        if not ok:
            return []
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
            return []

        found = []
        for observation in request.results() or []:
            box = observation.boundingBox()  # normalized, origin bottom-left
            bx = box.origin.x + box.size.width / 2
            by = box.origin.y + box.size.height / 2
            dist = float(np.hypot(bx - 0.5, by - 0.5))
            for candidate in observation.topCandidates_(1):
                value = parse_die_value(str(candidate.string()))
                if value is not None:
                    found.append((value, float(candidate.confidence()), dist))
        return found

    def read(self, frame: np.ndarray) -> Reading | None:
        h, w = frame.shape[:2]
        center = (w / 2, h / 2)
        candidates = list(self._ocr(frame))
        for step in range(1, ROTATIONS):
            matrix = cv2.getRotationMatrix2D(center, step * (360 / ROTATIONS), 1.0)
            candidates.extend(self._ocr(cv2.warpAffine(frame, matrix, (w, h))))
        return _select(candidates, self.name)
