"""Localhost WebSocket hub: fans roll events out to companion/overlay clients
and routes arm/confirm messages back to the watch loop."""
import asyncio
import json
import threading
from collections import deque

import websockets

HISTORY_SIZE = 50  # events replayed to a client that connects mid-session


class Hub:
    def __init__(self, port: int = 8777):
        self.port = port
        self.on_arm = None
        self.on_confirm = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set = set()
        self._history: deque = deque(maxlen=HISTORY_SIZE)
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self._error: Exception | None = None

    def start_in_thread(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=5) or self._error is not None:
            raise RuntimeError(f"hub failed to start on port {self.port}: {self._error}")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:
            self._error = exc
        finally:
            self._started.set()
            self._loop.close()

    async def _serve(self) -> None:
        self._stop_event = asyncio.Event()
        async with websockets.serve(self._handler, "127.0.0.1", self.port) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._started.set()
            await self._stop_event.wait()  # run until stop() sets the event

    async def _handler(self, ws) -> None:
        self._clients.add(ws)
        try:
            if self._history:
                await ws.send(json.dumps({"type": "history", "events": list(self._history)}))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                kind = msg.get("type")
                if kind == "arm":
                    if self.on_arm is not None:
                        try:
                            self.on_arm(msg)
                        except Exception:
                            pass
                    await self._send_all({
                        "type": "armed",
                        "label": msg.get("label"),
                        "die": msg.get("die"),
                    })
                elif kind == "confirm":
                    if self.on_confirm is not None and "roll_id" in msg and "value" in msg:
                        try:
                            self.on_confirm(msg["roll_id"], int(msg["value"]))
                        except Exception:
                            pass
        finally:
            self._clients.discard(ws)

    async def _send_all(self, event: dict) -> None:
        self._history.append(event)  # loop thread only; replayed to late joiners
        raw = json.dumps(event)
        for ws in list(self._clients):
            try:
                await ws.send(raw)
            except websockets.ConnectionClosed:
                self._clients.discard(ws)

    def broadcast(self, event: dict) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_all(event), self._loop)
        except RuntimeError:
            pass

    def stop(self) -> None:
        if self._loop is not None and not self._loop.is_closed() and self._stop_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)


def demo_events() -> list[dict]:
    return [
        {"type": "armed", "label": "Initiative", "die": "d20"},
        {"type": "result", "roll_id": "demo-000", "value": 17,
         "confidence": 0.95, "reader": "keypoints"},
        {"type": "armed", "label": "Wisdom Save", "die": "d20"},
        {"type": "unread", "roll_id": "demo-001"},
        {"type": "result", "roll_id": "demo-002", "value": 20,
         "confidence": 0.9, "reader": "haiku"},
    ]


def _demo_main() -> None:
    import argparse
    import itertools
    import time

    parser = argparse.ArgumentParser(prog="towereye.hub")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()
    hub = Hub(port=args.port)
    hub.on_confirm = lambda roll_id, value: print(f"confirm: {roll_id} -> {value}")
    hub.start_in_thread()
    print(f"Demo hub on ws://127.0.0.1:{hub.port} (Ctrl-C to stop)")
    try:
        for event in itertools.cycle(demo_events()):
            print("sending", event)
            hub.broadcast(event)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        hub.stop()


if __name__ == "__main__":
    _demo_main()
