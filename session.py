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

from brain import (HANGUP_TAG, Brain, build_system_prompt, stage_hint, clean_for_speech, humanize_reply,
                   is_farewell, split_for_speech, split_sentences, strip_farewell)
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
        prof_gender = ""
        hdr = {"Authorization": f"Bearer {token}"}
        # Avatar/tên: dùng ĐÚNG route app Flutter đang dùng (spiritwebs/v1/me -> avatar_url,
        # xem fetchMeSafe trong app_globals.dart), không dùng gravatar mặc định của WP.
        try:
            r2 = await c.get(base + "/wp-json/spiritwebs/v1/me", headers=hdr)
            if r2.status_code == 200:
                me = r2.json()
                me = me.get("data", me) if isinstance(me.get("data"), dict) else me
                avatar = str(me.get("avatar_url") or "")
                user_id = user_id or me.get("id") or me.get("user_id")
                name = me.get("display_name") or me.get("name") or me.get("username") or name
                prof_gender = me.get("gender") or me.get("sex") or ""
        except Exception as e:
            log.debug("spiritwebs/v1/me lỗi: %s", e)
        if not user_id or not name:
            try:
                me = (await c.get(base + "/wp-json/wp/v2/users/me", headers=hdr)).json()
                user_id = user_id or me.get("id")
                name = name or me.get("name")
            except Exception as e:
                log.debug("users/me lỗi: %s", e)
        log.info("Bot %s: avatar=%s", account["username"], avatar or "(trống)")
    if not user_id:
        raise RuntimeError(f"không suy ra được user_id cho {account['username']}")
    return {"username": account["username"], "token": token, "user_id": int(user_id),
            "display_name": name or account["username"], "avatar": avatar,
            "gender": account.get("gender") or prof_gender or None}


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
    BARGE_IN_MS = 600

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
        self._prep: Optional[asyncio.Task] = None
        self._t_offer = 0.0
        self._engine_task: Optional[asyncio.Task] = None
        self.engine = ""        # engine TTS chốt cho cả cuộc gọi ("" = cách cũ)

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
            # Chốt engine TTS (VieNeu hay edge) ngay lúc đổ chuông, để cả cuộc gọi dùng 1 giọng nhất quán.
            self._engine_task = asyncio.create_task(self.brain.choose_engine(
                self.persona.gender, self.persona.region, self.persona.username))
            self._tasks.append(self._engine_task)
            # Chuẩn bị sẵn offer + gom ICE candidate TRONG LÚC đổ chuông (STUN có thể mất tới ~5s),
            # để lúc adminroot bấm nghe là gửi offer được ngay.
            self._prep = asyncio.create_task(self._prepare_webrtc())
            self._tasks.append(self._prep)

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
            self._t_accept = time.perf_counter()
            await self._start_webrtc()
            # Chờ nối được HOẶC cuộc gọi bị kết thúc (reject/end từ app) — không ngồi chờ hết 20s vô ích.
            w_conn = asyncio.create_task(self.connected.wait())
            w_end = asyncio.create_task(self.ended.wait())
            try:
                await asyncio.wait({w_conn, w_end}, timeout=float(self.cfg.get("webrtc_connect_timeout_seconds", 45)),
                                   return_when=asyncio.FIRST_COMPLETED)   # app mở nguội (bị tắt hẳn) cần nhiều giây mới nối được
            finally:
                for t in (w_conn, w_end):
                    t.cancel()
            if not self.connected.is_set():
                if self.ended.is_set():
                    outcome = "rejected_after_accept" if "reject" in self.end_reason else "ended_before_connect"
                    log.info("Cuộc gọi kết thúc ngay sau khi nghe máy (%s)", self.end_reason)
                    return {"outcome": outcome, "reason": self.end_reason}
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
            if not event.startswith("webrtc_"):
                log.info("📩 sự kiện từ Phoenix: %s %s", event, str(payload)[:300])    # kèm nội dung để biết ai gửi (vd call_reject)
            if event == "call_accept":
                self.accepted.set()
            elif event in ("call_reject", "call_end", "call_timeout", "phx_close"):
                self.end_reason = event
                self.ended.set()
            elif event == "webrtc_answer":
                if self._t_offer:
                    log.info("⏱ nhận answer của app sau %.1fs kể từ lúc gửi offer", time.perf_counter() - self._t_offer)
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
    async def _prepare_webrtc(self):
        """Tạo PeerConnection + offer + gom ICE candidate (chạy sẵn khi đang đổ chuông)."""
        t0 = time.perf_counter()
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
        log.info("⏱ gom ICE xong sau %.1fs", time.perf_counter() - t0)

    async def _start_webrtc(self):
        if self._prep is None:
            self._prep = asyncio.create_task(self._prepare_webrtc())
        await self._prep
        self._t_offer = time.perf_counter()
        await self.room.push("webrtc_offer", {"sdp": self.pc.localDescription.sdp})
        log.info("⏱ gửi offer sau %.1fs kể từ lúc nghe máy", self._t_offer - getattr(self, "_t_accept", self._t_offer))

    # ---------------- nghe
    async def _listen(self, track):
        resample = FrameResampler16k()
        det = UtteranceDetector(silence_ms=int(self.cfg.get("vad_silence_ms", 600)),
                                min_threshold=float(self.cfg.get("vad_min_threshold", 250)))
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
                loud_ms = loud_ms + ms if rms > max(det.noise * 6, 1800.0) else 0.0
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
                i = det.last_info
                log.info("🎙 nghe xong 1 câu: dài %.1fs (tiếng nói %.1fs), chốt vì: %s, nền=%.0f ngưỡng=%.0f",
                         i.get("total_s", 0), i.get("speech_s", 0), i.get("reason", "?"),
                         i.get("noise", 0), i.get("thr", 0))
                await self._utt_q.put(utt)

    # ---------------- nói
    async def say(self, text: str, gemini: bool = False):
        text = clean_for_speech(text)
        if not text:
            return
        self._interrupted = False
        if self._engine_task is not None and not self.engine:
            try:
                self.engine = await asyncio.wait_for(asyncio.shield(self._engine_task), 25)
            except Exception:
                self.engine = "edge"
        # Gemini TTS không stream: nguyên đoạn dài = chờ lâu. Tách câu để câu đầu (ngắn) ra tiếng sớm,
        # các câu sau tổng hợp song song trong lúc câu đầu đang phát. Đặt tts.gemini_split=false để về cách cũ.
        tts_cfg = self.cfg["tts"]
        one_chunk = (tts_cfg.get("provider") == "gemini" and not tts_cfg.get("gemini_split", False)) \
            or (gemini and tts_cfg.get("gemini_first_turn", False) and tts_cfg.get("provider") != "vieneu")  # lượt đầu dùng Gemini: 1 request cho cả lượt (VieNeu thì vẫn tách câu để câu đầu ra tiếng sớm)
        sentences = [text] if one_chunk else split_for_speech(text)
        t_say = time.perf_counter()
        first = True
        tasks = [asyncio.create_task(self.brain.synth(s, self.persona.gender, self.persona.tts_rate, self.persona.region,
                                                   self.persona.tts_pitch, gemini=gemini,
                                                   voice_key=self.persona.username,
                                                   voice_override=self.persona.gemini_voice,
                                                   engine=self.engine)) for s in sentences]
        try:
            for t in tasks:
                pcm = await t
                if first:
                    first = False
                    log.info("⏱ TTS câu đầu sau %.1fs", time.perf_counter() - t_say)
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
        min_turns = int(cfg.get("min_turns_before_hangup", 6))
        reason = "ended_by_peer"

        # Người nghe máy thường nói "Alô?" trước.
        utt = await self._next_utterance(float(cfg.get("first_alo_wait_seconds", 3.0)))   # chờ "Alô?" ngắn thôi, im lâu quá thì bot mở lời
        heard = await self.brain.transcribe(utt, self.bot["token"]) if utt is not None else ""
        history.append({"role": "user",
                        "content": heard or "(anh Hùng vừa bắt máy, chưa nói gì — bạn mở lời trước)"})

        while not self.ended.is_set():
            if time.time() > deadline:
                reason = "max_call_seconds"
                await self.say(random.choice([
                    "Dạ thôi em không làm phiền anh nữa nha, chào anh.",
                    "Dạ vậy nha anh, em cúp máy nghen, chào anh.",
                ]))
                break

            t_llm = time.perf_counter()
            reply = await self.brain.reply(system + "\n\n" + stage_hint(self.turns, self.persona.scenario_tag), history)
            log.info("⏱ LLM %.1fs", time.perf_counter() - t_llm)
            if not reply:      # LLM hỏng: nói câu an toàn rồi kết thúc, đừng im lặng
                reason = "llm_failed"
                await self.say("Ơ mạng em hơi chập chờn, em gọi lại anh sau nha.")
                break
            hangup = HANGUP_TAG in reply
            suppressed = False
            if hangup and self.turns + 1 < min_turns:
                log.info("Bỏ qua thẻ cúp máy quá sớm (lượt %d < %d)", self.turns + 1, min_turns)
                hangup = False
                suppressed = True
            spoken = humanize_reply(clean_for_speech(reply))
            if hangup and not is_farewell(spoken):
                # Chỉ cúp khi câu thật sự là lời chào tạm biệt, không phải câu hỏi (tránh cúp ngang lúc đang hỏi anh).
                log.info("Bỏ thẻ cúp máy: câu không phải lời chào kết thúc (%r)", spoken[-40:])
                hangup = False
            if suppressed:
                spoken = strip_farewell(spoken)
            history.append({"role": "assistant", "content": spoken})
            self.turns += 1
            log.info("🤖 %s: %s", self.persona.call_name, spoken)
            await self.say(spoken, gemini=(self.turns == 1))      # lượt nói đầu của bot = lời chào -> Gemini
            if hangup:
                reason = "bot_hangup_tag"
                await asyncio.sleep(1.2)      # chờ đuôi lời chào kịp tới điện thoại rồi mới cúp, khỏi cụt chữ
                break
            if len(history) > 24:      # giữ ngữ cảnh gọn cho free-tier
                history = history[-24:]

            # chờ adminroot nói. Tiếng ồn/im lặng bị Whisper "bịa" (đã lọc -> rỗng) thì chờ tiếp, KHÔNG bắt bot
            # đòi "anh nói lại"; chỉ khi liên tiếp nhiều lần mới hỏi lại.
            heard, stop, ignored = "", False, 0
            while True:
                utt = await self._next_utterance(cfg["idle_hangup_seconds"])
                if utt is None:
                    idle += 1
                    if idle >= 2:
                        reason = "idle"
                        await self.say("Alô? Chắc anh đang bận, em gọi lại sau nha anh.")
                        stop = True
                    else:
                        history.append({"role": "user", "content": "(anh Hùng im lặng một lúc)"})
                    break
                idle = 0
                t_stt = time.perf_counter()
                heard = await self.brain.transcribe(utt, self.bot["token"])
                # Khách nói thêm trong lúc bot đang nói (đã xếp hàng): gộp chung 1 lượt thay vì đáp từng câu cũ một.
                while heard and not self._utt_q.empty():
                    more = await self.brain.transcribe(self._utt_q.get_nowait(), self.bot["token"])
                    if more:
                        heard = f"{heard} {more}"
                log.info("⏱ STT %.1fs", time.perf_counter() - t_stt)
                if heard:
                    break
                ignored += 1
                if ignored >= 3:
                    history.append({"role": "user", "content": "(không nghe rõ anh Hùng nói gì)"})
                    break
                log.info("STT rỗng/nhiễu (%d) -> chờ tiếp, chưa hỏi lại", ignored)
            if stop:
                break
            if heard:
                log.info("👤 adminroot: %s", heard)
                history.append({"role": "user", "content": heard})
        log.info("Kết thúc hội thoại. Lý do: %s (ended=%s, end_reason=%s)", reason, self.ended.is_set(), self.end_reason)