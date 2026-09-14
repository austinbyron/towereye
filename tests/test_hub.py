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
        await asyncio.wait_for(ws.recv(), timeout=2)  # join-time die message
        hub.broadcast({"type": "result", "roll_id": "r1", "value": 17,
                       "confidence": 0.95, "reader": "keypoints"})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["value"] == 17


@pytest.mark.asyncio
async def test_arm_triggers_callback_and_armed_broadcast(hub):
    seen = []
    hub.on_arm = seen.append
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        await asyncio.wait_for(ws.recv(), timeout=2)  # join-time die message
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
        await asyncio.wait_for(ws.recv(), timeout=2)  # join-time die message
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


@pytest.mark.asyncio
async def test_new_client_receives_recent_event_history(hub):
    hub.broadcast({"type": "result", "roll_id": "r1", "value": 12,
                   "confidence": 0.95, "reader": "keypoints"})
    hub.broadcast({"type": "timeout"})
    await asyncio.sleep(0.2)  # let the loop thread record them
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "history"
        assert [e["type"] for e in msg["events"]] == ["result", "timeout"]
        assert msg["events"][0]["value"] == 12


@pytest.mark.asyncio
async def test_client_with_no_history_gets_no_history_message(hub):
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        die = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert die["type"] == "die"  # the join-time die message, never a history one
        hub.broadcast({"type": "timeout"})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "timeout"  # next message is live, not history


def test_demo_events_are_valid_hub_traffic():
    from towereye.hub import demo_events

    events = demo_events()
    kinds = [e["type"] for e in events]
    assert "armed" in kinds and "result" in kinds and "unread" in kinds
    for e in events:
        if e["type"] == "result":
            assert {"roll_id", "value", "confidence", "reader"} <= e.keys()


@pytest.mark.asyncio
async def test_set_die_updates_hub_and_broadcasts_die_event(hub):
    seen = []
    hub.on_set_die = seen.append
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert first == {"type": "die", "die": "auto"}  # every client learns the current die on join
        await ws.send(json.dumps({"type": "set_die", "die": "d8"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg == {"type": "die", "die": "d8"}
    assert seen == ["d8"]
    assert hub.die == "d8"


@pytest.mark.asyncio
async def test_set_die_rejects_unknown_dice_silently(hub):
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        await asyncio.wait_for(ws.recv(), timeout=2)  # the join-time die message
        await ws.send(json.dumps({"type": "set_die", "die": "d7"}))
        hub.broadcast({"type": "timeout"})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "timeout"  # no die event went out
    assert hub.die == "auto"


@pytest.mark.asyncio
async def test_late_joiner_gets_the_selected_die_after_history(hub):
    hub.die = "d12"
    hub.broadcast({"type": "timeout"})
    await asyncio.sleep(0.2)
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        history = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert history["type"] == "history"
        die = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert die == {"type": "die", "die": "d12"}


@pytest.mark.asyncio
async def test_request_handler_reply_is_broadcast(hub):
    hub.on_request = lambda msg: {"type": "templates", "pools": {}} if msg["type"] == "templates" else None
    async with websockets.connect(f"ws://127.0.0.1:{hub.port}") as ws:
        await asyncio.wait_for(ws.recv(), timeout=2)  # join-time die message
        await ws.send(json.dumps({"type": "templates"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg == {"type": "templates", "pools": {}}
        await ws.send(json.dumps({"type": "mystery"}))  # handler says None: nothing goes out
        hub.broadcast({"type": "timeout"})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "timeout"
