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
