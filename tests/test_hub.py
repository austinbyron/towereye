import asyncio
import json

import pytest
import websockets

from towereye.hub import Hub


@pytest.fixture
def hub():
    h = Hub(port=0)  # 0 = pick a free port; Hub exposes .port after start
    h.start_in_thread()
    yield h
    h.stop()


@pytest.mark.asyncio
async def test_broadcast_reaches_client(hub):
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        hub.broadcast({"type": "result", "roll_id": "r1", "value": 17,
                       "confidence": 0.95, "reader": "keypoints"})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["value"] == 17


@pytest.mark.asyncio
async def test_arm_triggers_callback_and_armed_broadcast(hub):
    seen = []
    hub.on_arm = seen.append
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        await ws.send(json.dumps({"type": "arm", "label": "Initiative", "die": "d20"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg == {"type": "armed", "label": "Initiative", "die": "d20"}
    assert seen and seen[0]["label"] == "Initiative"


@pytest.mark.asyncio
async def test_confirm_triggers_callback(hub):
    seen = []
    hub.on_confirm = lambda roll_id, value: seen.append((roll_id, value))
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        await ws.send(json.dumps({"type": "confirm", "roll_id": "r1", "value": 18}))
        await asyncio.sleep(0.2)
    assert seen == [("r1", 18)]


@pytest.mark.asyncio
async def test_garbage_does_not_kill_connection(hub):
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        await ws.send("not json")
        await ws.send(json.dumps({"type": "mystery"}))
        await ws.send(json.dumps("5"))
        await ws.send(json.dumps([1, 2]))
        hub.broadcast({"type": "timeout"})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "timeout"


def test_occupied_port_raises_promptly():
    first = Hub(port=0)
    first.start_in_thread()
    try:
        second = Hub(port=first.port)
        with pytest.raises(RuntimeError):
            second.start_in_thread()
    finally:
        first.stop()


def test_broadcast_after_stop_is_noop(hub):
    hub.stop()
    hub.broadcast({"type": "timeout"})  # must not raise


def test_demo_events_are_valid_hub_traffic():
    from towereye.hub import demo_events

    events = demo_events()
    kinds = [e["type"] for e in events]
    assert "armed" in kinds and "result" in kinds and "unread" in kinds
    for e in events:
        if e["type"] == "result":
            assert {"roll_id", "value", "confidence", "reader"} <= e.keys()
