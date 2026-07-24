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
