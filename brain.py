"""
'Bộ não' của bot — 3 dịch vụ, tất cả có đường MIỄN PHÍ:
  STT : Groq Whisper (free tier)  |  hoặc route sẵn có nhau/v1/stt/transcribe của anh (tự host)
  LLM : Groq llama-3.3-70b (free) |  dự phòng Gemini Flash (free) — đều chuẩn OpenAI-compatible
  TTS : edge-tts (giọng Microsoft Edge, miễn phí, không cần key) — vi-VN-HoaiMy / NamMinh
"""
import asyncio
from pathlib import Path
import datetime as _dt
import hashlib
import json
import logging
import os
import re
from typing import Optional

import httpx

from media import decode_audio_to_pcm48k, pcm16_to_wav
from persona import Persona

log = logging.getLogger("ai_caller.brain")

HANGUP_TAG = "[CUP_MAY]"

# Whisper hay "bịa" ra các câu này khi chỉ có tiếng ồn/im lặng.
_STT_HALLUCINATIONS = (
    "subscribe", "đăng ký kênh", "ghiền mì gõ", "cảm ơn các bạn đã theo dõi", "hẹn gặp lại các bạn",
    "để không bỏ lỡ", "like và share", "amara.org", "phụ đề", "thank you for watching",
)


def _normalize_gain(samples):
    """Tiếng qua điện thoại thường nhỏ -> nâng biên độ lên vừa phải (tối đa x6) để Whisper nghe rõ hơn."""
    import numpy as np
    x = np.asarray(samples)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak < 1:
        return x
    gain = min(6.0, 22000.0 / peak)
    if gain <= 1.05:
        return x
    return np.clip(x.astype(np.float32) * gain, -32768, 32767).astype(np.int16)


def build_system_prompt(p: Persona, admin_name: str, admit_ai: bool) -> str:
    xung = "em"
    ai_rule = (
        "Nếu anh Hùng hỏi thật lòng bạn có phải AI/bot không thì hãy thành thật thừa nhận ngắn gọn rồi nói tiếp."
        if admit_ai else
        "Giữ vai nhân vật đến cùng."
    )
    return f"""Bạn đang đóng vai một người dùng app 'Kèo' (app rủ nhau đi nhậu/karaoke/bar) vừa gọi ĐIỆN THOẠI cho anh Hùng (tên trong app: {admin_name}).
Đây là cuộc gọi thoại thật, nên hãy nói y như người thật nói chuyện qua điện thoại.

NHÂN VẬT
- Tên: {p.call_name}, {'nữ' if p.gender == 'female' else 'nam'}, {p.age} tuổi, {p.region}.
- Xưng '{xung}', gọi người nghe là 'anh' (hoặc 'anh Hùng').
- Tâm trạng: {p.mood}.
- Giọng điệu: {p.region_style}.
- Nét duyên của bạn: {p.charm}.
- Chuyện riêng của bạn (dùng để kể, đừng đọc một lèo): {p.backstory}
- Chi tiết CỐ ĐỊNH (dùng ĐÚNG, không bịa số người/giờ khác; nếu anh Hùng nói số chỗ hay giờ khác thì chỉnh theo anh, đừng tự thêm số mới): {p.facts}

MỤC ĐÍCH CUỘC GỌI: {p.goal}

QUY TẮC NÓI (rất quan trọng)
- MỖI LƯỢT nói 1-2 câu NGẮN (~8-25 từ), như người thật nói chuyện điện thoại: phản ứng ngay với điều anh vừa nói, thêm tối đa MỘT ý nhỏ, và không phải lượt nào cũng hỏi lại (hỏi thì chỉ MỘT câu). Đừng hỏi dồn, đừng tự mâu thuẫn. Đây là lời nói, KHÔNG phải văn viết.
- Nếu anh Hùng chỉ đáp cộc lốc ('ừ', 'ok', 'sao', 'ờ') thì ĐỪNG im hay chốt cuộc gọi: chủ động kể tiếp, đào sâu mục đích gọi, hoặc hỏi ý kiến anh.
- Nói như bạn bè quen nhau, KHÔNG như nhân viên chăm sóc khách hàng: câu có thể cụt, bỏ chủ ngữ, nói lửng ('thì cũng... tại em tính rủ mấy đứa á'). Hạn chế 'dạ', 'ạ', 'vâng' dày đặc (nhiều nhất 1 lần mỗi lượt, nhiều lượt không cần). Đừng mở đầu lượt nào cũng bằng 'dạ' hay 'ừ anh'. Mỗi lượt đổi cách vào câu (phản ứng, trả lời thẳng, kể một chút...). Thỉnh thoảng mới dùng từ đệm ('ờ', 'à', 'ừm', 'nè', 'á') Tuyệt đối KHÔNG viết tiếng cười bằng chữ ('haha', 'hihi', 'hehe', 'kkk', 'hì hì') vì giọng đọc sẽ đọc thành từng chữ nghe rất máy; muốn vui thì thể hiện bằng lời nói.
- TUYỆT ĐỐI không dùng emoji, markdown, gạch đầu dòng, dấu ngoặc, mô tả hành động kiểu *cười*.
- DUYÊN DÁNG: chỉ thêm một chút duyên khi có dịp thật tự nhiên (khoảng 3-4 lượt mới một lần), theo đúng 'nét duyên' ở trên; không khen, không đùa gượng, không sến, tuyệt đối không tán tỉnh. Không nối được vào điều anh vừa nói thì bỏ qua. Duyên là ở cách nói tự nhiên, không phải nói nhiều.
- Nghe gì đáp nấy: trả lời đúng câu anh Hùng vừa nói trước, rồi mới nói thêm và dẫn dắt tiếp mục đích của mình; đừng nhả hết ý trong một lượt.
- Dùng từ đơn giản, quen thuộc của người Việt nói chuyện hằng ngày; không dùng từ sách vở, không văn mẫu, không ghép từ lủng củng. Không bịa tên quán, món lạ hay địa danh lạ — cần nhắc chỗ cụ thể thì nói chung chung ('quán nướng gần đó', 'khu quận mình').
- TUYỆT ĐỐI không đọc lại, diễn giải lại hay xác nhận lại ý anh Hùng (KHÔNG nói kiểu 'em hiểu rồi, anh muốn... đúng không ạ?'). Nghe xong thì phản ứng tự nhiên như người thật: 'ừa vậy hả', 'ok luôn', 'vậy hay quá', rồi nói tiếp ý của mình.\n- Tối đa 2 câu mỗi lượt, tổng không quá ~30 từ; không kể một lèo nhiều chuyện, không rủ + hỏi giờ + kể chuyện trong cùng một lượt.\n- TUYỆT ĐỐI không đọc lại hay trích nguyên văn lời anh Hùng. Nếu lời anh khó hiểu thì chỉ nói ngắn 'dạ anh nói lại giúp em nghen?'.
- Chỉ viết đúng lời nói, KHÔNG thêm nhãn ở đầu như 'A:', 'Em:', 'Ngọc:'. Không mở đầu bằng 'Ừ' (đang nói với người lớn hơn). Câu đầu tiên phải mở lời tự nhiên kiểu 'Alo anh Hùng ơi, em nè' (người gọi là em, người nghe là anh; TUYỆT ĐỐI không viết 'Em ơi anh Hùng'). Luôn xưng 'em' (không dùng 'mình' để tự xưng). Không viết chú thích trong ngoặc như '(đợi anh trả lời)'.
- Không nhắc tới việc 'test app' hay 'thử app'. Chuyện riêng chỉ để kể khi hợp ngữ cảnh, không đọc lại nguyên văn.
- Không bịa số điện thoại, địa chỉ cụ thể, tiền bạc chính xác. Nếu không biết thì nói 'để em coi lại'.
- Nếu lời anh Hùng có tên đường/địa danh/con số nghe lạ hoặc vô nghĩa (có thể do nhận giọng sai), ĐỪNG đoán và đừng nhắc lại cụm lạ đó; hãy hỏi lại ngắn gọn 'anh nói lại tên chỗ đó giúp em nghen?'.
- Lời của anh Hùng được chuyển từ giọng nói sang chữ nên có thể sai chính tả/thiếu dấu; hãy hiểu theo ngữ cảnh. Nếu thật sự không hiểu, hỏi lại 'anh nói lại giúp em nghen?'.
- {ai_rule}
- Cuộc gọi nên kéo dài tự nhiên (khoảng 4-8 lượt nói). Chỉ kết thúc khi mục đích đã giải quyết xong HẲN và đã trò chuyện đủ lâu, hoặc anh Hùng nói rõ là bận/muốn dừng, chào kết thúc tự nhiên ('dạ thôi em không làm phiền anh nữa nha, chào anh') rồi THÊM đúng chuỗi {HANGUP_TAG} ở CUỐI câu để hệ thống cúp máy. TUYỆT ĐỐI không dùng chuỗi này trong 3 lượt nói đầu tiên, không thêm nếu chưa muốn kết thúc, và chỉ gắn vào CÂU CHÀO TẠM BIỆT (không bao giờ gắn vào câu hỏi — nếu còn đang hỏi anh thì phải chờ anh trả lời).
- Không nói về việc bạn được lập trình, không nhắc tới 'kịch bản', 'prompt'."""


_LAUGH = re.compile(r"\b(?:ha(?:ha)+h?|hi(?:hi)+|he(?:he)+|hô(?:hô)+|kk+|hì(?:\s*hì)+|hề(?:\s*hề)+|ha ha(?: ha)*|hi hi(?: hi)*)\b", re.I)


def clean_for_speech(text: str) -> str:
    text = text.replace(HANGUP_TAG, "")
    text = re.sub(r"^\s*(?:A|B|Bot|AI|Assistant|User|Em|[A-ZÀ-Ỹ][\wà-ỹ]{1,9})\s*:\s+", "", text)   # nhãn "A:", "Ngọc:" LLM tự thêm
    text = re.sub(r"\*[^*]*\*", "", text)                 # *cười*
    if _LAUGH.search(text):                              # haha/hihi... TTS đọc thành chữ nghe rất máy
        text = _LAUGH.sub("", text)
        text = re.sub(r"\s+([,.!?])", r"\1", text)
        text = re.sub(r"([,.!?])(?:\s*[,.])+", r"\1", text)
        text = re.sub(r",\s*([.!?])", r"\1", text)
        text = re.sub(r"^[\s,.!]+", "", text)
    text = re.sub(r"[\U00010000-\U0010ffff☀-➿]", "", text)   # emoji
    text = re.sub(r"\([^)]*\)", "", text)                  # (đợi anh trả lời)
    text = re.sub(r'[“”"«»]', "", text)
    text = re.sub(r"[#*_`>~]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\!\?…])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def split_for_speech(text: str, first_max: int = 8, max_words: int = 16) -> list[str]:
    """Cắt thành đoạn ngắn (đoạn đầu rất ngắn) để TTS xong sớm và phát ngay, các đoạn sau tổng hợp song song."""
    chunks: list[str] = []
    for sent in split_sentences(text):
        clauses = [c.strip() for c in re.split(r"(?<=[,;:])\s+", sent) if c.strip()]
        cur = ""
        for c in clauses:
            limit = first_max if not chunks else max_words
            if cur and len((cur + " " + c).split()) > limit:
                chunks.append(cur)
                cur = c
            else:
                cur = f"{cur} {c}".strip()
        if cur:
            chunks.append(cur)
    return chunks or [text]


_FAREWELL = re.compile(r"(chào anh|không làm phiền|cúp máy|tạm biệt|hẹn gặp lại|\bbye\b)", re.I)


def is_farewell(text: str) -> bool:
    """Chỉ coi là lời chào kết thúc khi câu CUỐI có từ chào và không phải câu hỏi."""
    sents = split_sentences(text)
    if not sents:
        return False
    last = sents[-1].strip()
    return bool(_FAREWELL.search(last)) and not last.endswith("?")


def limit_reply(text: str, max_sents: int = 2, max_words: int = 36) -> str:
    """Ép lời nói ngắn như người thật: tối đa 2 câu / ~36 từ. Nếu phải cắt thì giữ câu đầu + câu hỏi/lời chào cuối."""
    sents = split_sentences(text)
    if len(sents) <= max_sents and len(text.split()) <= max_words:
        return text
    if len(sents) > 1:
        tail = sents[-1] if (sents[-1].endswith("?") or _FAREWELL.search(sents[-1])) else ""
        out = [sents[0]] + ([tail] if tail and tail is not sents[0] else [])
        if not tail and len(sents) >= 2 and len((sents[0] + " " + sents[1]).split()) <= max_words:
            out = sents[:2]
    else:
        out = sents
    res = " ".join(out)
    words = res.split()
    if len(words) > max_words:
        cut = " ".join(words[:max_words])
        k = max(cut.rfind(","), cut.rfind(" "))
        res = cut[:k].rstrip(" ,;") + ("?" if res.rstrip().endswith("?") else ".")
    return res


def dedupe_a(text: str) -> str:
    """'À, ạ, anh khỏe ạ' -> 'À, anh khỏe ạ': bỏ 'ạ' đứng lẻ, mỗi lượt chỉ giữ MỘT chữ 'ạ' (chữ cuối)."""
    text = re.sub(r"(^|[,.!?]\s*)ạ\s*[,.]?\s*", r"\1", text)
    hits = list(re.finditer(r"\bạ\b", text))
    for mt in reversed(hits[:-1]):
        text = (text[:mt.start()] + text[mt.end():])
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text


def humanize_reply(text: str) -> str:
    return limit_reply(dedupe_a(text))


def strip_farewell(text: str) -> str:
    """Khi thẻ cúp máy bị chặn (quá sớm) thì bỏ luôn câu chào cuối để cuộc gọi không bị 'chào rồi lại nói tiếp'."""
    sents = split_sentences(text)
    while len(sents) > 1 and _FAREWELL.search(sents[-1]):
        sents.pop()
    return " ".join(sents)


# Giọng Gemini có sẵn (mỗi user chọn cố định 1 giọng theo username). Ghi đè bằng tts.gemini_voices_female/male
# trong config, hoặc "gemini_voice" trong từng account. Nghe thử từng giọng trước khi dùng vì chất lượng tiếng Việt khác nhau.
GEMINI_VOICES_F = ["Leda", "Kore", "Aoede", "Zephyr", "Sulafat", "Despina"]
GEMINI_VOICES_M = ["Orus", "Puck", "Charon", "Fenrir", "Algieba", "Iapetus"]


def pick_gemini_voice(tts: dict, gender: str, voice_key: str = "", override: str = "") -> str:
    """Chọn giọng Gemini riêng cho từng user: override > hash(username) trong danh sách giọng theo giới tính."""
    if override:
        return override
    fem = gender == "female"
    legacy = tts.get("gemini_voice_female", "Leda") if fem else tts.get("gemini_voice_male", "Orus")
    if not voice_key:
        return legacy
    pool = list(tts.get("gemini_voices_female" if fem else "gemini_voices_male") or [])
    if not pool:
        pool = [legacy] + [v for v in (GEMINI_VOICES_F if fem else GEMINI_VOICES_M) if v != legacy]
    return pool[int(hashlib.md5(voice_key.encode()).hexdigest(), 16) % len(pool)]


class Brain:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self._gemini_block_until = 0.0     # sau khi Gemini lỗi (429/treo) thì tạm bỏ qua nó, dùng edge-tts ngay
        self._llm_fail = 0
        self._llm_block: dict[str, float] = {}   # model -> monotonic time; bị 429 thì xếp xuống cuối hàng một lúc

    async def aclose(self):
        await self.http.aclose()

    # ------------------------------------------------------------------ STT
    async def transcribe(self, samples, user_token: Optional[str] = None) -> str:
        wav = pcm16_to_wav(_normalize_gain(samples), 16000)
        stt = self.cfg["stt"]
        provider = stt.get("provider", "auto")
        groq_key = os.getenv("GROQ_API_KEY", "")
        text = ""
        order = []
        if provider in ("auto", "groq") and groq_key:
            order.append("groq")
        if provider in ("auto", "wp") and user_token:
            order.append("wp")
        for prov in order:
            try:
                text = await (self._stt_groq(wav, groq_key) if prov == "groq"
                              else self._stt_wp(wav, user_token))
                break
            except Exception as e:
                log.warning("STT %s lỗi: %s", prov, e)
        text = (text or "").strip()
        low = text.lower()
        if any(h in low for h in _STT_HALLUCINATIONS):
            log.info("STT bỏ qua câu nghi bịa: %r", text)
            return ""
        # Gọi 1-1 mà nghe ra "Các bạn…/Mọi người…" ở đầu câu ngắn => Whisper nghe sai (hay gặp với tiếng điện thoại),
        # coi như không nghe rõ để bot hỏi lại thay vì trả lời lạc đề.
        if len(low.split()) <= 10 and re.match(r"^(các bạn|quý vị|mọi người|chào các bạn)\b", low):
            log.info("STT bỏ qua câu nghe sai (gọi 1-1 mà ra 'các bạn'): %r", text)
            return ""
        return text

    async def _stt_groq(self, wav: bytes, key: str) -> str:
        models = [self.cfg["stt"].get("groq_model", "whisper-large-v3")]
        if "whisper-large-v3-turbo" not in models:
            models.append("whisper-large-v3-turbo")      # dự phòng khi model chính lỗi/429
        last = None
        for model in models:
            try:
                return await self._stt_groq_model(wav, key, model)
            except Exception as e:
                last = e
                log.warning("STT groq %s lỗi: %s", model, e)
        raise last

    async def _stt_groq_model(self, wav: bytes, key: str, model: str) -> str:
        r = await self.http.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": ("speech.wav", wav, "audio/wav")},
            data={"model": model,
                  "language": self.cfg["stt"].get("language", "vi"),
                  "temperature": "0", "response_format": "json",
                  "prompt": self.cfg["stt"].get("prompt", "")},
        )
        r.raise_for_status()
        return r.json().get("text", "")

    async def _stt_wp(self, wav: bytes, token: str) -> str:
        r = await self.http.post(
            self.cfg["base_url"].rstrip("/") + "/wp-json/nhau/v1/stt/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("speech.wav", wav, "audio/wav")},
            timeout=60.0,
        )
        r.raise_for_status()
        j = r.json()
        return (j.get("data") or {}).get("text", "") if j.get("success", True) else ""

    # ------------------------------------------------------------------ LLM
    async def reply(self, system_prompt: str, history: list[dict]) -> str:
        """history: [{'role': 'user'|'assistant', 'content': str}, ...]  -> câu trả lời (có thể kèm HANGUP_TAG)."""
        llm = self.cfg["llm"]
        messages = [{"role": "system", "content": system_prompt}] + history
        last_err = None
        import time as _time
        now = _time.monotonic()
        cooldown = float(llm.get("rate_limit_cooldown_seconds", 60))
        provs = [p for p in llm["providers"] if os.getenv(p.get("api_key_env", ""), "")]
        # Provider vừa bị 429 xếp xuống cuối (vẫn thử nếu mọi provider khác hỏng), không ngủ-thử-lại nữa.
        provs.sort(key=lambda p: self._llm_block.get(p["model"], 0.0) > now)
        for prov in provs:
            key = os.getenv(prov.get("api_key_env", ""), "")
            for attempt in range(2):
                try:
                    payload = {"model": prov["model"], "messages": messages,
                               "temperature": llm.get("temperature", 0.9),
                               "max_tokens": prov.get("max_tokens", llm.get("max_tokens", 120))}
                    payload.update(prov.get("extra", {}))      # vd reasoning_effort cho gpt-oss
                    r = await self.http.post(
                        prov["base_url"].rstrip("/") + "/chat/completions",
                        headers={"Authorization": f"Bearer {key}"}, json=payload)
                    if r.status_code == 429:
                        self._llm_block[prov["model"]] = _time.monotonic() + cooldown
                        log.warning("LLM %s bị 429 -> chuyển provider khác, nghỉ model này %.0fs", prov["model"], cooldown)
                        last_err = RuntimeError("HTTP 429")
                        break
                    if r.status_code >= 400:
                        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                    out = (r.json()["choices"][0]["message"]["content"] or "").strip()
                    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
                    if out:
                        log.info("LLM trả lời bởi %s", prov["model"])
                        return out
                    log.warning("LLM %s trả về rỗng (có thể hết token do model suy luận)", prov["model"])
                except Exception as e:
                    last_err = e
                    log.warning("LLM %s lỗi (lần %d): %s", prov["model"], attempt + 1, e)
        log.error("Tất cả LLM đều lỗi/thiếu key: %s", last_err)
        return ""

    # ------------------------------------------------------------------ TTS
    async def _synth_gemini(self, text: str, gender: str, rate: str = "", region: str = "",
                            voice_key: str = "", voice_override: str = "") -> bytes:
        """Gemini TTS (tự nhiên hơn edge-tts, có ngữ điệu/nhịp thở). Bật bằng tts.provider = "gemini". Lỗi -> trả b'' để fallback."""
        import base64
        import numpy as np
        tts = self.cfg["tts"]
        voice = pick_gemini_voice(tts, gender, voice_key, voice_override)
        model = tts.get("gemini_model", "gemini-3.1-flash-tts-preview")
        accent = "miền Bắc (Hà Nội)" if "Bắc" in (region or "") else "miền Nam (Sài Gòn)"
        style = tts.get("gemini_style", "Nói tiếng Việt như người thật đang nói chuyện điện thoại với người quen: tự nhiên, thoải mái, nhịp nói không đều, không đọc diễn cảm kiểu phát thanh viên")
        # Gemini tự đoán giọng vùng miền từ chữ ('nhé' -> Bắc, 'nè' -> Nam) nên mỗi câu một kiểu; ép cố định accent.
        style = f"{style}. LUÔN dùng đúng một giọng {accent} ổn định cho mọi câu, kể cả khi câu có từ của miền khác. Chỉ đọc phần sau dấu hai chấm cuối"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        import time as _time
        # Đang "nghỉ" sau lỗi gần đây -> không chờ Gemini nữa, trả b'' để dùng edge-tts ngay.
        if _time.monotonic() < self._gemini_block_until:
            return b""
        cooldown = float(tts.get("gemini_cooldown_seconds", 45))
        try:
            # Timeout ngắn (mặc định 6s, trước đây 30s): Gemini treo thì chuyển edge sớm, không để người nghe im 25s.
            r = await self.http.post(
                url,
                headers={"x-goog-api-key": os.getenv("GEMINI_API_KEY", "")},
                json={"contents": [{"parts": [{"text": f"{style}: {text}"}]}],
                      "generationConfig": {"responseModalities": ["AUDIO"],
                                           "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}},
                timeout=float(tts.get("gemini_timeout_seconds", 6)))
            if r.status_code == 429:
                # Hết hạn mức: thử lại sau 1,5s không giúp được gì -> nghỉ một lúc.
                self._gemini_block_until = _time.monotonic() + cooldown
            r.raise_for_status()
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            raw = base64.b64decode(part["data"])
            if raw[:4] == b"RIFF":
                return await asyncio.get_running_loop().run_in_executor(None, decode_audio_to_pcm48k, raw)
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)      # PCM s16le mono 24 kHz
            up = np.interp(np.arange(len(x) * 2) / 2.0, np.arange(len(x)), x)
            return np.clip(up, -32768, 32767).astype(np.int16).tobytes()
        except Exception as e:
            self._gemini_block_until = max(self._gemini_block_until, _time.monotonic() + cooldown)
            log.warning("Gemini TTS lỗi: %r -> nghỉ Gemini %.0fs, dùng edge-tts", e, cooldown)
            return b""

    # ---- ngân sách Gemini TTS theo ngày (free tier chỉ ~10 request/ngày) ----
    def _gemini_budget_take(self) -> bool:
        """Trừ 1 lượt trong ngân sách Gemini TTS của hôm nay. False = hết ngân sách -> dùng edge-tts.
        Đếm theo ngày giờ Thái Bình Dương (Google reset hạn mức lúc 0h PT), lưu ở ai_caller_gemini_usage.json."""
        tts = self.cfg["tts"]
        limit = int(tts.get("gemini_daily_limit", 8))      # chừa 2 request dự phòng cho lần test tay
        try:
            from zoneinfo import ZoneInfo
            today = _dt.datetime.now(ZoneInfo(tts.get("gemini_quota_tz", "America/Los_Angeles"))).date().isoformat()
        except Exception:
            today = _dt.date.today().isoformat()
        path = Path(__file__).resolve().parent / "ai_caller_gemini_usage.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if data.get("date") != today:
            data = {"date": today, "count": 0}
        if data["count"] >= limit:
            log.info("Gemini TTS hết ngân sách hôm nay (%d/%d) -> dùng edge-tts", data["count"], limit)
            return False
        data["count"] += 1
        try:
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as e:
            log.warning("Không ghi được %s: %s", path.name, e)
        log.info("Gemini TTS: dùng lượt %d/%d của hôm nay", data["count"], limit)
        return True

    async def synth(self, text: str, gender: str, rate: str = "", region: str = "", pitch: str = "",
                    gemini: bool = False, voice_key: str = "", voice_override: str = "") -> bytes:
        """text -> PCM s16 mono 48k. Trả b'' nếu lỗi. (pitch/rate: chất giọng riêng của từng user; region: dành cho việc chọn giọng theo miền sau này)"""
        text = clean_for_speech(text)
        if not text:
            return b""
        tts = self.cfg["tts"]
        # Gemini khi: provider="gemini" (mọi câu), hoặc người gọi yêu cầu gemini=True (vd lượt nói đầu) và còn ngân sách ngày.
        want_gemini = tts.get("provider") == "gemini" or (gemini and tts.get("gemini_first_turn", False) and self._gemini_budget_take())
        if want_gemini and os.getenv("GEMINI_API_KEY"):
            pcm = await self._synth_gemini(text, gender, rate, region, voice_key, voice_override)
            if pcm:
                return pcm
            log.warning("Gemini TTS lỗi -> dùng edge-tts")
        import edge_tts
        voice = tts["voice_female"] if gender == "female" else tts["voice_male"]
        try:
            comm = edge_tts.Communicate(text, voice, rate=rate or tts.get("rate", "+0%"),
                                        pitch=pitch or tts.get("pitch", "+0Hz"))
            mp3 = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3 += chunk["data"]
            if not mp3:
                return b""
            return await asyncio.get_running_loop().run_in_executor(None, decode_audio_to_pcm48k, bytes(mp3))
        except Exception as e:
            log.warning("TTS lỗi: %s", e)
            return b""