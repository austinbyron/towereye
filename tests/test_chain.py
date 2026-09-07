import numpy as np

from towereye.readers import Reading, ReaderChain, parse_die_value

FRAME = np.zeros((10, 10, 3), dtype=np.uint8)


class FakeReader:
    def __init__(self, name, reading):
        self.name = name
        self._reading = reading
        self.called = False
        self.seen = None

    def read(self, frame):
        self.called = True
        self.seen = frame
        return self._reading


def test_parse_die_value():
    assert parse_die_value("17") == 17
    assert parse_die_value(" 6.\n") == 6   # underline/dot marks on d20 faces
    assert parse_die_value("9_") == 9
    assert parse_die_value("21") is None   # out of range
    assert parse_die_value("0") is None
    assert parse_die_value("01") is None   # upside-down 10, not a 1
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


def test_chain_never_returns_a_weak_guess():
    # a wrong number in chat is worse than a reroll: no best-effort guesses
    weak1 = FakeReader("a", Reading(value=6, confidence=0.2, reader="a"))
    weak2 = FakeReader("b", Reading(value=9, confidence=0.4, reader="b"))
    chain = ReaderChain([weak1, weak2], min_confidence=0.5)
    assert chain.read(FRAME) is None


def test_chain_retries_alternate_crops_before_giving_up():
    f = np.zeros((200, 200, 3), dtype=np.uint8)
    f[20:90, 100:170] = (255, 120, 100)
    class Flaky:
        name = "flaky"
        def __init__(self):
            self.shapes = []
        def read(self, crop):
            self.shapes.append(crop.shape[0])
            return Reading(value=4, confidence=0.9, reader=self.name) if len(self.shapes) == 2 else None
    reader = Flaky()
    assert ReaderChain([reader]).read(f).value == 4
    assert len(reader.shapes) == 2 and reader.shapes[1] > reader.shapes[0]  # second try was the wider crop


def test_chain_returns_none_when_all_fail():
    chain = ReaderChain([FakeReader("a", None), FakeReader("b", None)])
    assert chain.read(FRAME) is None


def test_chain_hands_readers_the_topface_crop():
    f = np.zeros((200, 200, 3), dtype=np.uint8)
    f[20:90, 100:170] = (255, 120, 100)  # die-sized blob away from frame center
    reader = FakeReader("a", Reading(value=4, confidence=0.9, reader="a"))
    ReaderChain([reader]).read(f)
    assert reader.seen.shape[0] < 70  # cropped to the top face, not the full frame


def test_chain_passes_full_frame_when_no_die_found():
    reader = FakeReader("a", Reading(value=4, confidence=0.9, reader="a"))
    ReaderChain([reader]).read(FRAME)
    assert reader.seen is FRAME
