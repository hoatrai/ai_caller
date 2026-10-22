"""
Một cuộc gọi thoại: bot (user test) -> adminroot, qua đúng giao thức app đang dùng:
  Phoenix room:chat_X_Y  ->  init_user -> call_invite -> (adminroot bấm Nghe) call_accept
  -> bot tạo WebRTC offer (giống isCaller trong video_call_page.dart) -> webrtc_answer/ice
  -> nói chuyện: nghe (VAD) -> STT -> LLM -> TTS -> phát lại qua track audio.
"""
import asyncio
import re
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

from autoadmin import (ADMIN_OPENERS, admin_opener, admin_reply_limits, admin_turn_shape, build_admin_prompt,
                       collapse_repeat, relation_of, southernize)
from brain import (turn_shape, soften_vocative, HANGUP_TAG, Brain, build_system_prompt, stage_hint, clean_for_speech, humanize_reply,
                   is_farewell, limit_reply, split_for_speech, split_sentences, strip_farewell)
from media import BotVoiceTrack, FrameResampler16k, UtteranceDetector
from persona import HANH_TAG, ROMANTIC_TAGS, SMART_TAG, Persona, _fold
from rhythm import jitter_rate, pause_after_ms, polish_chunk, silence_pcm
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


_END_RE = re.compile(r"\b(cup|tat|dap|ngat)\s+(may|nha|nhe|nghen|day|di|thoi|luon)\b|\bthoi\s+cup\b|\bbye\b|\btam biet\b")


def _wants_to_end(text: str) -> bool:
    """Anh Hùng nói muốn cúp máy ('cúp máy nha', 'thôi cúp đi', 'tắt máy', 'bye'...)."""
    return bool(_END_RE.search(_fold(text or "")))


class CallSession:
    BARGE_IN_MS = 600

    def __init__(self, cfg: dict, brain: Brain, bot: dict, persona: Persona, admin_id: int, auto_admin: bool = False):
        self.cfg, self.brain, self.bot, self.persona = cfg, brain, bot, persona
        self.admin_id = admin_id
        # Chế độ auto-admin: adminroot thật chỉ nghe, AI đóng vai adminroot trả lời bot (xem autoadmin.py).
        self.auto_admin = auto_admin
        _a = cfg.get("auto_admin") or {}
        self._auto = _a
        self._admin_system = ""
        self._admin_shapes: list[int] = []     # các kiểu lượt admin ảo đã dùng (cho vai người yêu thông minh)
        self.admin_vp = {"gender": _a.get("gender", "male"), "region": _a.get("region", "Nam"),
                         "rate": _a.get("rate", ""), "pitch": _a.get("pitch", ""),
                         "voice_key": _a.get("voice_key", "adminroot"), "voice_override": _a.get("gemini_voice", "")}
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
        self._fillers: list[bytes] = []          # tiếng đệm "ờm...", "à..." tổng hợp sẵn (che khoảng chờ LLM)
        self._filler_task: Optional[asyncio.Task] = None
        self._last_filler = -1

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
                # Chờ server trả lời + nghỉ chút để tin call_end kịp tới app TRƯỚC khi đóng WebRTC/WebSocket
                # (trước đây đẩy xong là đóng ngay, app có thể không kịp nhận nên đồng hồ cuộc gọi cứ chạy tiếp).
                await self.room.push("call_end", {})      # server không trả lời sự kiện này (đã thử chờ: luôn timeout) nên không chờ reply
                log.info("📴 đã gửi call_end cho app")
                await asyncio.sleep(0.6)
            else:
                log.info("📴 không gửi call_end (ended=%s, room_closed=%s, lý do=%s)",
                         self.ended.is_set(), self.room.closed.is_set(), self.end_reason)
        except Exception as e:
            log.warning("📴 gửi call_end lỗi hoặc server không trả lời: %r", e)
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
                # auto-admin: không nghe/không STT/không chen ngang (adminroot chỉ nghe), chỉ xả frame cho khỏi dồn bộ nhớ.
                self._tasks.append(asyncio.create_task(self._drain(track) if self.auto_admin else self._listen(track)))

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
    async def _drain(self, track):
        while not self.ended.is_set():
            try:
                await track.recv()
            except Exception:
                break

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
    async def say(self, text: str, gemini: bool = False, vp: Optional[dict] = None):
        """vp: hồ sơ giọng khác (gender/region/rate/pitch/voice_key/voice_override), dùng cho admin ảo. None = giọng của bot."""
        text = clean_for_speech(text)
        if not text:
            return
        vp = vp or {"gender": self.persona.gender, "region": self.persona.region, "rate": self.persona.tts_rate,
                    "pitch": self.persona.tts_pitch, "voice_key": self.persona.username,
                    "voice_override": self.persona.gemini_voice}
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
        human = bool(tts_cfg.get("human_rhythm", True))
        scale = float(tts_cfg.get("pause_scale", 1.0))
        base_rate = vp["rate"] or tts_cfg.get("rate", "")
        rates = [jitter_rate(base_rate, s_) if human else vp["rate"] for s_ in sentences]
        t_say = time.perf_counter()
        first = True
        tasks = [asyncio.create_task(self.brain.synth(s_, vp["gender"], rates[i], vp["region"],
                                                   vp["pitch"], gemini=gemini,
                                                   voice_key=vp["voice_key"],
                                                   voice_override=vp["voice_override"],
                                                   engine=self.engine)) for i, s_ in enumerate(sentences)]
        try:
            for i, t in enumerate(tasks):
                pcm = await t
                if first:
                    first = False
                    log.info("⏱ TTS câu đầu sau %.1fs", time.perf_counter() - t_say)
                if self._interrupted or self.ended.is_set():
                    break
                if human:
                    # Nhịp người thật: cắt khoảng lặng thừa của TTS, vuốt đầu/cuối, rồi tự ngắt hơi theo dấu câu
                    # (phẩy ngắn, chấm/hỏi dài hơn, ba chấm lâu nhất) thay vì nối sát rạt hoặc hở ngẫu nhiên.
                    if pcm:
                        pcm = polish_chunk(pcm)
                        if i < len(tasks) - 1:
                            pcm += silence_pcm(pause_after_ms(sentences[i], scale))
                    self.voice.speak(pcm)       # xếp hàng liền, không chờ phát xong từng đoạn
                    continue
                self.voice.speak(pcm)
                # Chờ câu này phát xong rồi mới tới câu sau (để chen ngang có tác dụng giữa các câu).
                await self.voice.wait_done()
                if self._interrupted:
                    break
            if human and not self._interrupted:
                await self.voice.wait_done()
        finally:
            for t in tasks:
                t.cancel()

    # ---------------- tiếng đệm che khoảng chờ
    def _start_filler_prewarm(self):
        """Sau lời chào đầu tiên, tổng hợp sẵn vài tiếng đệm cùng giọng (trong lúc anh đang nói, không tranh với lượt đáp)."""
        tts_cfg = self.cfg["tts"]
        if self._filler_task or not tts_cfg.get("human_rhythm", True) or not tts_cfg.get("filler", True):
            return
        self._filler_task = asyncio.create_task(self._prewarm_fillers())
        self._tasks.append(self._filler_task)

    async def _prewarm_fillers(self):
        tts_cfg = self.cfg["tts"]
        texts = tts_cfg.get("filler_texts") or ["Ờm...", "À...", "Ừm..."]
        for tx in texts:
            if self.ended.is_set():
                return
            try:
                pcm = await self.brain.synth(tx, self.persona.gender, self.persona.tts_rate, self.persona.region,
                                             self.persona.tts_pitch, voice_key=self.persona.username,
                                             voice_override=self.persona.gemini_voice, engine=self.engine)
            except Exception as e:
                log.debug("filler lỗi: %s", e)
                continue
            if pcm:
                self._fillers.append(polish_chunk(pcm) + silence_pcm(90))
        log.info("Đã chuẩn bị %d tiếng đệm", len(self._fillers))

    async def _reply_with_filler(self, system: str, history: list[dict]) -> str:
        """Gọi LLM; nếu quá lâu chưa có câu trả lời thì nói 1 tiếng đệm ('ờm...') như người đang nghĩ, khỏi im bặt."""
        task = asyncio.create_task(self.brain.reply(system, history, smart=(self.persona.scenario_tag in (SMART_TAG, HANH_TAG))))
        try:
            tts_cfg = self.cfg["tts"]
            if self.turns >= 1 and self._fillers and tts_cfg.get("human_rhythm", True) and tts_cfg.get("filler", True):
                done, _ = await asyncio.wait({task}, timeout=float(tts_cfg.get("filler_after_seconds", 1.3)))
                if (not done and not self.ended.is_set() and not self.voice.is_speaking
                        and random.random() < 0.8):
                    choices = [i for i in range(len(self._fillers)) if i != self._last_filler] or [0]
                    self._last_filler = random.choice(choices)
                    self.voice.speak(self._fillers[self._last_filler])
                    log.info("💭 tiếng đệm #%d (LLM chưa xong)", self._last_filler)
            return await task
        except BaseException:
            task.cancel()
            raise

    async def _next_utterance(self, timeout: float):
        try:
            return await asyncio.wait_for(self._utt_q.get(), timeout)
        except asyncio.TimeoutError:
            return None

    # ---------------- auto-admin: AI đóng vai adminroot (người thật chỉ nghe)
    async def _auto_admin_open(self, admin_hist: list[dict]) -> str:
        """Admin ảo nhấc máy nói 'Alô' trước (giống người thật), rồi bot mới mở lời."""
        line = admin_opener(self.persona)
        admin_hist.append({"role": "assistant", "content": line})
        log.info("🧑‍💼 adminroot(AI): %s", line)
        await self.say(line, vp=self.admin_vp)
        return line

    async def _auto_admin_reply(self, bot_line: str, admin_hist: list[dict]) -> str:
        """Đưa lời bot cho admin ảo, lấy câu đáp, đọc ra bằng giọng riêng. Trả '' nếu LLM hỏng."""
        admin_hist.append({"role": "user", "content": bot_line})
        if len(admin_hist) > 24:
            del admin_hist[:-24]
        await asyncio.sleep(random.uniform(0.3, 0.9))       # nghỉ nhẹ như người thật nghĩ trước khi đáp
        reply = ""
        rel = relation_of(self.persona)
        system, smart = self._admin_system, False
        if rel == "lover":      # vai người yêu thông minh: mỗi lượt một kiểu nói, model suy luận kỹ hơn (tắt: auto_admin.smart=false)
            si, hint = admin_turn_shape(self._admin_shapes, len(self._admin_shapes))
            self._admin_shapes.append(si)
            log.info("🎲 admin kiểu lượt #%d", si)
            system = self._admin_system + "\n\n" + hint
            smart = bool(self._auto.get("smart", True))
        for _ in range(2):
            reply = await self.brain.reply(system, admin_hist, smart=smart)
            if reply or self.ended.is_set():
                break
            await asyncio.sleep(2.0)
        _ms, _mw = admin_reply_limits(rel)
        reply = limit_reply(collapse_repeat(southernize(clean_for_speech(reply))), max_sents=_ms, max_words=_mw) if reply else ""
        if not reply:
            admin_hist.pop()
            return ""
        admin_hist.append({"role": "assistant", "content": reply})
        log.info("🧑‍💼 adminroot(AI): %s", reply)
        await self.say(reply, vp=self.admin_vp)
        return reply

    # ---------------- hội thoại
    async def _conversation(self):
        cfg = self.cfg
        system = build_system_prompt(self.persona, cfg["admin_username"], cfg.get("admit_ai_if_asked", True))
        history: list[dict] = []
        deadline = time.time() + cfg["max_call_seconds"]
        idle = 0
        min_turns = int(cfg.get("min_turns_before_hangup", 6))
        romantic = self.persona.scenario_tag in ROMANTIC_TAGS
        end_requested = False      # cuộc gọi tình yêu: chỉ cúp khi anh Hùng nói muốn cúp máy
        if romantic:
            deadline = time.time() + int(cfg.get("romantic_max_call_seconds", 3600))     # mặc định tối đa 1 giờ
        reason = "ended_by_peer"
        shape_hist: list[int] = []     # các kiểu lượt đã dùng (vai thông minh bốc kiểu khác nhau mỗi lượt)
        admin_hist: list[dict] = []    # lịch sử của admin ảo (vai đảo: lời bot = user, lời admin ảo = assistant)
        auto_max_turns = int(self._auto.get("max_turns", 20))
        if self.auto_admin:
            deadline = time.time() + int(self._auto.get("max_seconds", 300))      # auto: giới hạn riêng, kể cả vai tình yêu
            self._admin_system = build_admin_prompt(self.persona, cfg["admin_username"], self._auto.get("extra", ""))
            log.info("🎭 auto-admin BẬT: adminroot chỉ nghe, AI trả lời bot (tối đa %d lượt / %ds)",
                     auto_max_turns, int(self._auto.get("max_seconds", 300)))

        if self.auto_admin:
            heard = await self._auto_admin_open(admin_hist)
        else:
            # Người nghe máy thường nói "Alô?" trước.
            utt = await self._next_utterance(float(cfg.get("first_alo_wait_seconds", 3.0)))   # chờ "Alô?" ngắn thôi, im lâu quá thì bot mở lời
            heard = await self.brain.transcribe(utt, self.bot["token"]) if utt is not None else ""
        history.append({"role": "user",
                        "content": heard or "(anh Hùng vừa bắt máy, chưa nói gì — bạn mở lời trước)"})

        while not self.ended.is_set():
            if time.time() > deadline or (self.auto_admin and self.turns >= auto_max_turns):
                reason = "max_call_seconds"
                await self.say(random.choice(["Thôi em cúp nha, thương anh. Mai mình nói chuyện tiếp ha.",
                     "Em phải đi rồi nè... nhớ anh nghen. Ngủ ngon, mai gọi lại.",
                     "Ui hết giờ rồi. Thương anh nhiều, bye bye nghen."] if romantic else [
                    "Dạ thôi em không làm phiền anh nữa nha, chào anh.",
                    "Dạ vậy nha anh, em cúp máy nghen, chào anh.",
                ]))
                break

            t_llm = time.perf_counter()
            end_hint = ("\n\nANH HÙNG VỪA NÓI MUỐN CÚP MÁY: chào tạm biệt kiểu NGƯỜI YÊU, 1-2 câu ngắn, ấm và hơi lưu luyến: dặn nhẹ một câu (ngủ ngon / nghỉ ngơi / đi đường cẩn thận), hẹn nói chuyện tiếp, nói 'thương anh'. TUYỆT ĐỐI KHÔNG dùng 'không làm phiền', 'chào anh', 'xin phép', giọng lịch sự xã giao. Không hỏi thêm gì. Rồi THÊM thẻ cúp máy ở cuối câu chào."
                        if end_requested else "")
            if end_requested and self.persona.scenario_tag == HANH_TAG:
                end_hint = "\n\nANH HÙNG VỪA NÓI MUỐN CÚP MÁY: em nghẹn lại, nói MỘT câu cuối thật ngắn, không hỏi thêm, không chào xã giao, PHẢI có chữ 'em cúp máy' (ví dụ 'Vậy thôi... em cúp máy.'), rồi THÊM thẻ cúp máy ở cuối."
            turn_prompt = system + "\n\n" + stage_hint(self.turns, self.persona.scenario_tag, self.persona.opener) + end_hint
            if self.persona.scenario_tag == SMART_TAG and not end_requested and self.turns >= 1:
                shape_i, shape_line = turn_shape(shape_hist, self.turns)
                shape_hist.append(shape_i)
                turn_prompt += "\n\n" + shape_line
                log.info("🎲 kiểu lượt #%d", shape_i)
            reply = await self._reply_with_filler(turn_prompt, history)
            log.info("⏱ LLM %.1fs", time.perf_counter() - t_llm)
            if not reply:      # mọi LLM cùng lỗi (429/503...): xin chờ chút rồi thử lại vài lần, đừng cúp ngay
                for k in range(int(cfg.get("llm_retry_attempts", 3))):
                    if self.ended.is_set():
                        break
                    if k == 0:
                        await self.say(random.choice([
                            "Ơ chờ em xíu nghen, mạng em hơi chậm.",
                            "Ờ khoan, đợi em chút nha, em nghe không rõ lắm.",
                        ]))
                    await asyncio.sleep(float(cfg.get("llm_retry_wait_seconds", 5)))
                    log.info("Thử lại LLM lần %d sau khi tất cả provider lỗi", k + 1)
                    reply = await self.brain.reply(turn_prompt, history, smart=(self.persona.scenario_tag in (SMART_TAG, HANH_TAG)))
                    if reply:
                        break
            if not reply:      # LLM hỏng hẳn: nói câu an toàn rồi kết thúc, đừng im lặng
                reason = "llm_failed"
                await self.say("Ơ mạng em hơi chập chờn, em gọi lại anh sau nha.")
                break
            hangup = HANGUP_TAG in reply
            suppressed = False
            if romantic and self.persona.scenario_tag != HANH_TAG:
                if hangup and not end_requested:
                    log.info("Bỏ thẻ cúp máy: kịch bản tình yêu, anh Hùng chưa nói cúp máy")
                    hangup = False
                    suppressed = True
            elif hangup and self.turns + 1 < min_turns:
                log.info("Bỏ qua thẻ cúp máy quá sớm (lượt %d < %d)", self.turns + 1, min_turns)
                hangup = False
                suppressed = True
            spoken = humanize_reply(clean_for_speech(reply), smart=(self.persona.scenario_tag in (SMART_TAG, HANH_TAG)))
            if romantic and self.persona.scenario_tag != HANH_TAG:
                spoken = soften_vocative(spoken, history)
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
            self._start_filler_prewarm()      # chuẩn bị tiếng đệm trong lúc chờ anh nói
            if hangup:
                reason = "bot_hangup_tag"
                await asyncio.sleep(1.2)      # chờ đuôi lời chào kịp tới điện thoại rồi mới cúp, khỏi cụt chữ
                break
            if len(history) > 12:      # giữ ngữ cảnh gọn cho free-tier
                history = history[-12:]

            # chờ adminroot nói. Tiếng ồn/im lặng bị Whisper "bịa" (đã lọc -> rỗng) thì chờ tiếp, KHÔNG bắt bot
            # đòi "anh nói lại"; chỉ khi liên tiếp nhiều lần mới hỏi lại.
            heard, stop, ignored = "", False, 0
            while True:
                if self.auto_admin:      # admin ảo đáp thay người thật (không STT, không chờ im lặng)
                    heard = await self._auto_admin_reply(spoken, admin_hist)
                    if not heard:
                        reason, stop = "auto_admin_failed", True
                    break
                utt = await self._next_utterance(cfg["idle_hangup_seconds"])
                if utt is None:
                    idle += 1
                    if idle >= 2 and not romantic:
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
                if romantic and _wants_to_end(heard):
                    end_requested = True
                    log.info("Anh Hùng nói muốn cúp máy -> bot chào rồi cúp")
                history.append({"role": "user", "content": heard})
        log.info("Kết thúc hội thoại. Lý do: %s (ended=%s, end_reason=%s)", reason, self.ended.is_set(), self.end_reason)