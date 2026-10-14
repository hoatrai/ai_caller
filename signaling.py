"""
Client Phoenix Channels tối giản (async) — bắt chước đúng cách app Flutter nói
chuyện với Phoenix: serializer JSON v1 (message là object
{topic,event,payload,ref}), không query param, 1 socket / 1 topic room:chat_X_Y.
"""
import asyncio
import json
import logging
from typing import Optional

import websockets

log = logging.getLogger("ai_caller.ws")


class PhoenixRoom:
    def __init__(self, url: str, topic: str):
        self.url = url
        self.topic = topic
        self.ws = None
        self._ref = 0
        self._pending: dict[str, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue()   # (event, payload) từ người kia / server
        self.closed = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    async def connect(self):
        self.ws = await websockets.connect(self.url, ping_interval=None, max_size=2 ** 22,
                                           open_timeout=15)
        self._tasks.append(asyncio.create_task(self._recv_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))

    async def _recv_loop(self):
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                ref = msg.get("ref")
                event = msg.get("event")
                if event == "phx_reply" and ref in self._pending:
                    fut = self._pending.pop(ref)
                    if not fut.done():
                        fut.set_result(msg.get("payload") or {})
                    continue
                if event in ("phx_close", "phx_error"):
                    log.warning("channel %s: %s", self.topic, event)
                    self.closed.set()
                    await self.events.put(("phx_close", {}))
                    continue
                if msg.get("topic") == self.topic:
                    await self.events.put((event, msg.get("payload") or {}))
        except Exception as e:  # kết nối rớt
            log.warning("ws recv lỗi: %s", e)
        finally:
            self.closed.set()
            await self.events.put(("phx_close", {}))

    async def _heartbeat_loop(self):
        try:
            while not self.closed.is_set():
                await asyncio.sleep(25)
                await self._send({"topic": "phoenix", "event": "heartbeat", "payload": {}, "ref": self._next_ref()})
        except Exception:
            pass

    async def _send(self, obj: dict):
        await self.ws.send(json.dumps(obj))

    async def push(self, event: str, payload: Optional[dict] = None, wait_reply: bool = False,
                   timeout: float = 10.0) -> Optional[dict]:
        ref = self._next_ref()
        fut = None
        if wait_reply:
            fut = asyncio.get_running_loop().create_future()
            self._pending[ref] = fut
        await self._send({"topic": self.topic, "event": event, "payload": payload or {}, "ref": ref})
        if fut is None:
            return None
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(ref, None)

    async def join(self):
        reply = await self.push("phx_join", {}, wait_reply=True)
        if (reply or {}).get("status") != "ok":
            raise RuntimeError(f"join thất bại: {reply}")

    async def close(self):
        for t in self._tasks:
            t.cancel()
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
