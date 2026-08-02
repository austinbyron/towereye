"""Cloud fallback reader: one Claude Haiku vision call per settled roll."""
import base64

import anthropic
import cv2
import numpy as np

from . import Reading, parse_die_value

PROMPT = (
    "This is a close-up of the top face of a 20-sided die (d20). The top-face "
    "numeral is the one at the CENTER of the image; partial numerals near the "
    "edges belong to side faces - ignore them. The numeral may be rotated at "
    "any angle, so consider every orientation. On this die, 6 and 9 are "
    "disambiguated by a period or underline AFTER the digit (e.g. '6.' is six). "
    "Reply with only the integer (1-20) on the top face, nothing else."
)

MIN_SIDE = 300  # upscale tiny top-face crops so the numeral is legible


class HaikuReader:
    name = "haiku"
    MODEL = "claude-haiku-4-5"

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()
        self.calls = 0

    def read(self, frame: np.ndarray) -> Reading | None:
        h, w = frame.shape[:2]
        if max(h, w) < MIN_SIDE:
            # no edge-trim here: off-center crops get leading digits sliced (19 -> 9)
            scale = MIN_SIDE / max(h, w)
            frame = cv2.resize(
                frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC
            )
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
        except (anthropic.APIError, TypeError):
            # TypeError: SDK raises it at request time when no API key is set;
            # a keyless session should fall through the chain, not crash watch.
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        value = parse_die_value(text)
        if value is None:
            return None
        # Haiku gives no confidence score; a parseable in-range answer is trusted.
        return Reading(value=value, confidence=0.9, reader=self.name)
