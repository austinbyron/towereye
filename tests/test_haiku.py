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


def test_small_crop_is_upscaled_untrimmed_before_sending():
    import base64

    import cv2

    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    frame[0:8, 0:8] = (0, 0, 255)  # corner content must SURVIVE: trimming was
    client = _mock_client("17")     # slicing leading digits (19 -> 9) off-center
    HaikuReader(client=client).read(frame)
    data = client.messages.create.call_args.kwargs["messages"][0]["content"][0]["source"]["data"]
    jpg = np.frombuffer(base64.standard_b64decode(data), dtype=np.uint8)
    sent = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
    assert max(sent.shape[:2]) >= 300
    assert sent[..., 2].max() > 150  # corner content still present


def test_garbage_reply_returns_none():
    reader = HaikuReader(client=_mock_client("I cannot tell"))
    assert reader.read(FRAME) is None


def test_missing_auth_returns_none():
    client = MagicMock()
    client.messages.create.side_effect = TypeError(
        "Could not resolve authentication method."
    )
    reader = HaikuReader(client=client)
    assert reader.read(FRAME) is None


def test_api_error_returns_none():
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com")
    )
    reader = HaikuReader(client=client)
    assert reader.read(FRAME) is None
    assert reader.calls == 1  # failed calls still count toward the session counter
