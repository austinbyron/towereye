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
