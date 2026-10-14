"""
Một cuộc gọi thoại: bot (user test) -> adminroot, qua đúng giao thức app đang dùng:
  Phoenix room:chat_X_Y  ->  init_user -> call_invite -> (adminroot bấm Nghe) call_accept
  -> bot tạo WebRTC offer (giống isCaller trong video_call_page.dart) -> webrtc_answer/ice
  -> nói chuyện: nghe (VAD) -> STT -> LLM -> TTS -> phát lại qua track audio.
"""
import asyncio
import collections
import logging
import random
import time
from typing import Optional

import httpx
import numpy as np
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError
from aiortc.sdp import candidate_from_sdp

from brain import HANGUP_TAG, Brain, build_system_prompt, clean_for_speech, split_sentences
from media import BotVoiceTrack, FrameResampler16k, UtteranceDetector
from persona import Persona
from signaling import PhoenixRoom

log = logging.getLogger("ai_caller.session")


# ---------------------------------------------------------------- WordPress login
async def login_bot(cfg: dict, account: dict) -> dict:
    """Đăng nhập JWT, lấy user_id + tên hiển thị + avatar (giống simulate.login_all)."""
    base = cfg["base_url"].rstrip("/")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(base + "/wp-json/jwt-auth/v1/token",
                         json={"username": account["username"], "password": account["password"]})
        r.raise_for_status()
        data = r.json()
        token = data.get("token") or (data.get("data") or {}).get("token")
        if not token:
            raise RuntimeError(f"login không có token cho {account['username']}")
        user_id = data.get("user_id") or data.get("id") or (data.get("data") or {}).get("user_id")
        name = data.get("user_display_name") or data.get("display_name") or ""
        avatar = ""
        try:
            me = (await c.get(base + "/wp-json/wp/v2/users/me",
                              headers={"Authorization": f"Bearer {token}"})).json()
            user_id = user_id or me.get("id")
            name = me.get("name") or name
            avatars = me.get("avatar_urls") or {}
            avatar = avatars.get("96") or next(iter(avatars.values()), "")
        except Exception as e:
            log.debug("users/me lỗi: %s", e)
    if not user_id:
        raise RuntimeError(f"không suy ra được user_id cho {account['username']}")
    return {"username": account["username"], "token": token, "user_id": int(user_id),
            "display_name": name or account["username"], "avatar": avatar,
            "gender": account.get("gender")}


async def resolve_admin_id(cfg: dict, token: str) -> int:
    if int(cfg.get("admin_user_id") or 0) > 0:
        return int(cfg["admin_user_id"])
    base = cfg["base_url"].rstrip("/")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(base + "/wp-json/wp/v2/users", params={"slug": cfg["admin_username"]},
                        headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200 and r.json():
            return int(r.json()[0]["id"])
    raise RuntimeError("Không tự tra được user_id của adminroot — điền 'admin_user_id' vào config.json")


# ---------------------------------------------------------------- Call session
class CallSession:
    BARGE_IN_MS = 350

    def __init__(self, cfg: dict, brain: Brain, bot: dict, persona: Persona, admin_id: int):
        self.cfg, self.brain, self.bot, self.persona = cfg, brain, bot, persona
        self.admin_id = admin_id
        # CHỐT AN TOÀN: phiên này chỉ được phép gọi đúng adminroot.
        if admin_id <= 0 or admin_id == bot["user_id"]:
            raise ValueError("admin_user_id không hợp lệ")
        a, b = sorted([bot["user_id"], admin_id])
        self.topic = f"room:chat_{a}_{b}"
        self.room = PhoenixRoom(cfg["websocket_url"], self.topic)
        self.pc: Optional[RTCPeerConnection] = None
        self.voice = BotVoiceTrack()
        self.accepted = asyncio.Event()
        self.ended = asyncio.Event()
        self.end_reason = ""
        self.connected = asyncio.Event()
        self._remote_set = asyncio.Event()
        self._early_ice: list[dict] = []
        self._utt_q: asyncio.Queue = asyncio.Queue()
        self._interrupted = False
        self._tasks: list[asyncio.Task] = []
        self.turns = 0
        self.started_at = 0.0

    # ---------------- vòng đời
    async def run(self) -> dict:
        outcome = "error"
        try:
            await self.room.connect()
            await self.room.join()
            await self.room.push("init_user", {"user_id": self.bot["user_id"],
                                               "username": self.bot["display_name"]},
                                 wait_reply=True)
            self._tasks.append(asyncio.create_task(self._dispatch()))
            await self.room.push("call_invite", {
                "from_id": self.bot["user_id"],
                "from_name": self.bot["display_name"],
                "from_avatar": self.bot["avatar"],
                "call_type": "voice",
            })
            log.info("📞 %s đang gọi adminroot (topic=%s, kịch bản=%s)",
                     self.bot["username"], self.topic, self.persona.scenario_tag)

            try:
                await asyncio.wait_for(self._wait_accept(), self.cfg["ring_timeout_seconds"])
            except asyncio.TimeoutError:
                outcome = "no_answer"
                await self.room.push("call_end", {})      # server sẽ gửi FCM huỷ chuông
                return {"outcome": outcome}
            if not self.accepted.is_set():
                outcome = "rejected" if "reject" in self.end_reason else "ended_early"
                return {"outcome": outcome}

            log.info("✅ adminroot đã nghe máy -> bắt đầu WebRTC")
            await self._start_webrtc()
            try:
                await asyncio.wait_for(self.connected.wait(), 20)
            except asyncio.TimeoutError:
                outcome = "webrtc_failed"
                await self.room.push("call_end", {})
                return {"outcome": outcome}

            self.started_at = time.time()
            await self._conversation()
            outcome = "completed"
            return {"outcome": outcome, "turns": self.turns, "seconds": int(time.time() - self.started_at)}
        finally:
            await self._cleanup()

    async def _wait_accept(self):
        while not self.accepted.is_set() and not self.ended.is_set():
            await asyncio.sleep(0.2)

    async def _cleanup(self):
        try:
            if not self.ended.is_set() and not self.room.closed.is_set():
                await self.room.push("call_end", {})
        except Exception:
            pass
        for t in self._tasks:
            t.cancel()
        if self.pc:
            try:
                await self.pc.close()
            except Exception:
                pass
        await self.room.close()

    # ---------------- tín hiệu từ Phoenix
    async def _dispatch(self):
        while True:
            event, payload = await self.room.events.get()
            if event == "call_accept":
                self.accepted.set()
            elif event in ("call_reject", "call_end", "call_timeout", "phx_close"):
                self.end_reason = event
                self.ended.set()
            elif event == "webrtc_answer":
                if self.pc and payload.get("sdp"):
                    try:
                        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=payload["sdp"], type="answer"))
                        self._remote_set.set()
                        for p in self._early_ice:
                            await self._add_ice(p)
                        self._early_ice.clear()
                    except Exception as e:
                        log.warning("setRemoteDescription lỗi: %s", e)
            elif event == "webrtc_ice":
                if self._remote_set.is_set():
                    await self._add_ice(payload)
                else:
                    self._early_ice.append(payload)

    async def _add_ice(self, p: dict):
        cand = (p.get("candidate") or "").strip()
        if not cand or not self.pc:
            return
        try:
            if cand.startswith("candidate:"):
                cand = cand[len("candidate:"):]
            ice = candidate_from_sdp(cand)
            ice.sdpMid = p.get("sdpMid")
            ice.sdpMLineIndex = p.get("sdpMLineIndex")
            await self.pc.addIceCandidate(ice)
        except Exception as e:
            log.debug("bỏ qua ICE lỗi: %s", e)

    # ---------------- WebRTC
    async def _start_webrtc(self):
        servers = [RTCIceServer(**s) for s in self.cfg["ice_servers"]]
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=servers))
        self.pc.addTrack(self.voice)

        @self.pc.on("connectionstatechange")
        async def _on_state():
            st = self.pc.connectionState
            log.info("WebRTC: %s", st)
            if st == "connected":
                self.connected.set()
            elif st in ("failed", "closed"):
                self.end_reason = f"webrtc_{st}"
                self.ended.set()

        @self.pc.on("track")
        def _on_track(track):
            if track.kind == "audio":
                self._tasks.append(asyncio.create_task(self._listen(track)))

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        # aiortc gom đủ ICE candidate vào SDP trước khi setLocalDescription trả về -> không cần trickle.
        await self.room.push("webrtc_offer", {"sdp": self.pc.localDescription.sdp})

    # ---------------- nghe
    async def _listen(self, track):
        resample = FrameResampler16k()
        det = UtteranceDetector()
        recent = collections.deque(maxlen=25)      # ~0.5s gần nhất (mỗi frame 20ms)
        loud_ms = 0.0
        while not self.ended.is_set():
            try:
                frame = await track.recv()
            except MediaStreamError:
                break
            except Exception as e:
                log.debug("recv lỗi: %s", e)
                break
            samples = resample(frame)
            if samples.size == 0:
                continue
            ms = samples.size * 1000.0 / 16000

            if self.voice.is_speaking:
                # Đang nói: không đưa vào VAD (tránh nghe lại chính mình), chỉ canh người kia chen ngang.
                recent.append(samples)
                rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                loud_ms = loud_ms + ms if rms > max(det.noise * 5, 1200.0) else 0.0
                if loud_ms >= self.BARGE_IN_MS:
                    log.info("✋ adminroot chen ngang -> bot im")
                    self.voice.stop_speaking()
                    self._interrupted = True
                    det.reset()
                    for s in recent:
                        det.feed(s)
                    recent.clear()
                    loud_ms = 0.0
                continue

            recent.clear()
            loud_ms = 0.0
            utt = det.feed(samples)
            if utt is not None:
                await self._utt_q.put(utt)

    # ---------------- nói
    async def say(self, text: str):
        text = clean_for_speech(text)
        if not text:
            return
        self._interrupted = False
        sentences = split_sentences(text) or [text]
        tasks = [asyncio.create_task(self.brain.synth(s, self.persona.gender)) for s in sentences]
        try:
            for t in tasks:
                pcm = await t
                if self._interrupted or self.ended.is_set():
                    break
                self.voice.speak(pcm)
                # Chờ câu này phát xong rồi mới tới câu sau (để chen ngang có tác dụng giữa các câu).
                await self.voice.wait_done()
                if self._interrupted:
                    break
        finally:
            for t in tasks:
                t.cancel()

    async def _next_utterance(self, timeout: float):
        try:
            return await asyncio.wait_for(self._utt_q.get(), timeout)
        except asyncio.TimeoutError:
            return None

    # ---------------- hội thoại
    async def _conversation(self):
        cfg = self.cfg
        system = build_system_prompt(self.persona, cfg["admin_username"], cfg.get("admit_ai_if_asked", True))
        history: list[dict] = []
        deadline = time.time() + cfg["max_call_seconds"]
        idle = 0

        # Người nghe máy thường nói "Alô?" trước.
        utt = await self._next_utterance(6.0)
        heard = await self.brain.transcribe(utt, self.bot["token"]) if utt is not None else ""
        history.append({"role": "user",
                        "content": heard or "(anh Admin vừa bắt máy, chưa nói gì — bạn mở lời trước)"})

        while not self.ended.is_set():
            if time.time() > deadline:
                await self.say(random.choice([
                    "Dạ thôi em không làm phiền anh nữa nha, chào anh.",
                    "Dạ vậy nha anh, em cúp máy nghen, chào anh.",
                ]))
                break

            reply = await self.brain.reply(system, history)
            if not reply:      # LLM hỏng: nói câu an toàn rồi kết thúc, đừng im lặng
                await self.say("Ơ mạng em hơi chập chờn, em gọi lại anh sau nha.")
                break
            hangup = HANGUP_TAG in reply
            spoken = clean_for_speech(reply)
            history.append({"role": "assistant", "content": reply.replace(HANGUP_TAG, "").strip()})
            self.turns += 1
            log.info("🤖 %s: %s", self.persona.call_name, spoken)
            await self.say(spoken)
            if hangup:
                break
            if len(history) > 24:      # giữ ngữ cảnh gọn cho free-tier
                history = history[-24:]

            # chờ adminroot nói
            utt = await self._next_utterance(cfg["idle_hangup_seconds"])
            if utt is None:
                idle += 1
                if idle >= 2:
                    await self.say("Alô? Chắc anh đang bận, em gọi lại sau nha anh.")
                    break
                history.append({"role": "user", "content": "(anh Admin im lặng một lúc)"})
                continue
            idle = 0
            heard = await self.brain.transcribe(utt, self.bot["token"])
            if not heard:
                history.append({"role": "user", "content": "(không nghe rõ anh Admin nói gì)"})
                continue
            log.info("👤 adminroot: %s", heard)
            history.append({"role": "user", "content": heard})
