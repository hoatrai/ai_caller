"""
Test end-to-end KHÔNG cần mạng ngoài: giả lập Phoenix server + giả lập 'adminroot' (aiortc),
mock STT/LLM/TTS. Kiểm tra: call_invite -> call_accept -> offer/answer -> audio 2 chiều
-> bot nói -> admin nói -> bot trả lời -> bot cúp máy.
Chạy:  python tests/test_e2e.py
"""
import asyncio
import fractions
import json
import math
import os
import sys
import time

import numpy as np
import websockets
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import session as session_mod
from config import DEFAULTS, _merge
from persona import make_persona

BOT_ID, ADMIN_ID = 7, 1
TOPIC = f"room:chat_{ADMIN_ID}_{BOT_ID}"
PORT = 18765


# ---------------- Phoenix giả
CLIENTS: list = []


async def fake_phoenix(ws):
    CLIENTS.append(ws)
    try:
        async for raw in ws:
            m = json.loads(raw)
            ev, ref = m["event"], m.get("ref")
            if ev in ("phx_join", "init_user", "heartbeat"):
                await ws.send(json.dumps({"topic": m["topic"], "event": "phx_reply", "ref": ref,
                                          "payload": {"status": "ok", "response": {}}}))
                continue
            for other in list(CLIENTS):          # broadcast_from!
                if other is not ws:
                    await other.send(json.dumps({"topic": m["topic"], "event": ev, "payload": m["payload"], "ref": None}))
    finally:
        CLIENTS.remove(ws)


# ---------------- admin giả
class ToneTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.t0 = None
        self.n = 0
        self.speak_from = None
        self.speak_for = 1.5

    async def recv(self):
        if self.t0 is None:
            self.t0 = time.time()
        else:
            self.n += 960
            w = self.t0 + self.n / 48000 - time.time()
            if w > 0:
                await asyncio.sleep(w)
        elapsed = self.n / 48000
        loud = self.speak_from is not None and self.speak_from <= elapsed < self.speak_from + self.speak_for
        t = (np.arange(960) + self.n) / 48000
        x = (np.sin(2 * math.pi * 300 * t) * (9000 if loud else 0)).astype(np.int16)
        f = AudioFrame(format="s16", layout="mono", samples=960)
        f.planes[0].update(x.tobytes())
        f.sample_rate = 48000
        f.pts = self.n
        f.time_base = fractions.Fraction(1, 48000)
        return f


async def fake_admin(result: dict):
    import websockets as ws_
    ws = await ws_.connect(f"ws://127.0.0.1:{PORT}/")
    ref = 0

    async def send(ev, payload):
        nonlocal ref
        ref += 1
        await ws.send(json.dumps({"topic": TOPIC, "event": ev, "payload": payload, "ref": str(ref)}))

    await send("phx_join", {})
    pc = RTCPeerConnection()
    tone = ToneTrack()
    pc.addTrack(tone)
    result["bot_frames_loud"] = 0

    @pc.on("track")
    def on_track(track):
        async def rd():
            try:
                while True:
                    fr = await track.recv()
                    a = fr.to_ndarray()
                    if np.abs(a.astype(np.int32)).mean() > 300:
                        result["bot_frames_loud"] += 1
            except MediaStreamError:
                pass
        asyncio.create_task(rd())

    async for raw in ws:
        m = json.loads(raw)
        ev, p = m["event"], m["payload"]
        if ev == "call_invite":
            result["invite"] = p
            await send("call_accept", {})
        elif ev == "webrtc_offer":
            await pc.setRemoteDescription(RTCSessionDescription(sdp=p["sdp"], type="offer"))
            ans = await pc.createAnswer()
            await pc.setLocalDescription(ans)
            await send("webrtc_answer", {"sdp": pc.localDescription.sdp})

            async def talk_later():
                await asyncio.sleep(3.0)           # sau khi bot mở lời xong
                tone.speak_from = tone.n / 48000
                result["admin_spoke"] = True
                await asyncio.sleep(5.0)
                tone.speak_from = tone.n / 48000      # nói lần 2
            asyncio.create_task(talk_later())
        elif ev == "call_end":
            result["bot_hung_up"] = True
            break
    await pc.close()
    await ws.close()


# ---------------- brain giả
class FakeBrain:
    def __init__(self):
        self.replies = ["Alo anh ơi, em hỏi tí nha. Tối nay anh rảnh không? [CUP_MAY]",
                        "Dạ anh nói sao em chưa nghe rõ nè.",
                        "Dạ vậy hẹn anh tối nay nha, chào anh. [CUP_MAY]"]
        self.heard = []

    async def transcribe(self, samples, token=None):
        self.heard.append(len(samples))
        return "tối nay anh rảnh nè"

    async def reply(self, system, history):
        return self.replies.pop(0) if self.replies else "ok [CUP_MAY]"

    async def synth(self, text, gender, rate="", region="", pitch="", gemini=False, **kw):
        n = int(48000 * 1.2)
        t = np.arange(n) / 48000
        return (np.sin(2 * math.pi * 440 * t) * 8000).astype(np.int16).tobytes()

    async def aclose(self):
        pass


async def main():
    server = await websockets.serve(fake_phoenix, "127.0.0.1", PORT)
    cfg = _merge(DEFAULTS, {"websocket_url": f"ws://127.0.0.1:{PORT}/", "ring_timeout_seconds": 5,
                            "max_call_seconds": 40, "idle_hangup_seconds": 8, "ice_servers": []})
    bot = {"username": "duonganh", "token": "x", "user_id": BOT_ID, "display_name": "Dương Anh",
           "avatar": "", "gender": None}
    persona = make_persona({"username": "duonganh"}, "Dương Anh")
    result = {}
    admin_task = asyncio.create_task(fake_admin(result))
    await asyncio.sleep(0.3)
    brain = FakeBrain()
    sess = session_mod.CallSession(cfg, brain, bot, persona, ADMIN_ID)
    res = await asyncio.wait_for(sess.run(), 60)
    await asyncio.wait_for(admin_task, 10)
    server.close()

    print("kết quả session:", res)
    print("invite payload:", result.get("invite"))
    print("bot_frames_loud:", result["bot_frames_loud"], "| admin nói:", result.get("admin_spoke"),
          "| STT nhận:", brain.heard, "| bot cúp máy:", result.get("bot_hung_up"))
    assert res["outcome"] == "completed", res
    assert result["invite"]["call_type"] == "voice" and result["invite"]["from_id"] == BOT_ID
    assert result["bot_frames_loud"] > 50, "admin không nhận được giọng bot"
    assert brain.heard and brain.heard[0] > 8000, "bot không nghe được giọng admin"
    assert res["turns"] == 3, res   # thẻ cúp máy ở lượt 1 phải bị bỏ qua
    assert result.get("bot_hung_up")
    print("E2E OK")


asyncio.run(main())
