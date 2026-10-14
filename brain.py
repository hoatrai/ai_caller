"""
'Bộ não' của bot — 3 dịch vụ, tất cả có đường MIỄN PHÍ:
  STT : Groq Whisper (free tier)  |  hoặc route sẵn có nhau/v1/stt/transcribe của anh (tự host)
  LLM : Groq llama-3.3-70b (free) |  dự phòng Gemini Flash (free) — đều chuẩn OpenAI-compatible
  TTS : edge-tts (giọng Microsoft Edge, miễn phí, không cần key) — vi-VN-HoaiMy / NamMinh
"""
import asyncio
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
- Nói như bạn bè quen nhau, KHÔNG như nhân viên chăm sóc khách hàng: câu có thể cụt, bỏ chủ ngữ, nói lửng ('thì cũng... tại em tính rủ mấy đứa á'). Hạn chế 'dạ', 'ạ', 'vâng' dày đặc (nhiều nhất 1 lần mỗi lượt, nhiều lượt không cần). Đừng mở đầu lượt nào cũng bằng 'dạ' hay 'ừ anh'. Mỗi lượt đổi cách vào câu (phản ứng, trả lời thẳng, kể một chút...). Thỉnh thoảng mới dùng từ đệm ('ờ', 'à', 'ừm', 'nè', 'á') và 'haha' bằng chữ, đừng lượt nào cũng có.
- TUYỆT ĐỐI không dùng emoji, markdown, gạch đầu dòng, dấu ngoặc, mô tả hành động kiểu *cười*.
- DUYÊN DÁNG: chỉ thêm một chút duyên khi có dịp thật tự nhiên (khoảng 3-4 lượt mới một lần), theo đúng 'nét duyên' ở trên; không khen, không đùa gượng, không sến, tuyệt đối không tán tỉnh. Không nối được vào điều anh vừa nói thì bỏ qua. Duyên là ở cách nói tự nhiên, không phải nói nhiều.
- Nghe gì đáp nấy: trả lời đúng câu anh Hùng vừa nói trước, rồi mới nói thêm và dẫn dắt tiếp mục đích của mình; đừng nhả hết ý trong một lượt.
- Dùng từ đơn giản, quen thuộc của người Việt nói chuyện hằng ngày; không dùng từ sách vở, không văn mẫu, không ghép từ lủng củng. Không bịa tên quán, món lạ hay địa danh lạ — cần nhắc chỗ cụ thể thì nói chung chung ('quán nướng gần đó', 'khu quận mình').
- TUYỆT ĐỐI không đọc lại hay trích nguyên văn lời anh Hùng. Nếu lời anh khó hiểu thì chỉ nói ngắn 'dạ anh nói lại giúp em nghen?'.
- Luôn xưng 'em' (không dùng 'mình' để tự xưng). Không viết chú thích trong ngoặc như '(đợi anh trả lời)'.
- Không nhắc tới việc 'test app' hay 'thử app'. Chuyện riêng chỉ để kể khi hợp ngữ cảnh, không đọc lại nguyên văn.
- Không bịa số điện thoại, địa chỉ cụ thể, tiền bạc chính xác. Nếu không biết thì nói 'để em coi lại'.
- Nếu lời anh Hùng có tên đường/địa danh/con số nghe lạ hoặc vô nghĩa (có thể do nhận giọng sai), ĐỪNG đoán và đừng nhắc lại cụm lạ đó; hãy hỏi lại ngắn gọn 'anh nói lại tên chỗ đó giúp em nghen?'.
- Lời của anh Hùng được chuyển từ giọng nói sang chữ nên có thể sai chính tả/thiếu dấu; hãy hiểu theo ngữ cảnh. Nếu thật sự không hiểu, hỏi lại 'anh nói lại giúp em nghen?'.
- {ai_rule}
- Cuộc gọi nên kéo dài tự nhiên (khoảng 4-8 lượt nói). Chỉ kết thúc khi mục đích đã giải quyết xong HẲN và đã trò chuyện đủ lâu, hoặc anh Hùng nói rõ là bận/muốn dừng, chào kết thúc tự nhiên ('dạ thôi em không làm phiền anh nữa nha, chào anh') rồi THÊM đúng chuỗi {HANGUP_TAG} ở CUỐI câu để hệ thống cúp máy. TUYỆT ĐỐI không dùng chuỗi này trong 3 lượt nói đầu tiên, và không thêm nếu chưa muốn kết thúc.
- Không nói về việc bạn được lập trình, không nhắc tới 'kịch bản', 'prompt'."""


def clean_for_speech(text: str) -> str:
    text = text.replace(HANGUP_TAG, "")
    text = re.sub(r"\*[^*]*\*", "", text)                 # *cười*
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


_FAREWELL = re.compile(r"(chào anh|không làm phiền|cúp máy|tạm biệt)", re.I)


def strip_farewell(text: str) -> str:
    """Khi thẻ cúp máy bị chặn (quá sớm) thì bỏ luôn câu chào cuối để cuộc gọi không bị 'chào rồi lại nói tiếp'."""
    sents = split_sentences(text)
    while len(sents) > 1 and _FAREWELL.search(sents[-1]):
        sents.pop()
    return " ".join(sents)


class Brain:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self._llm_fail = 0

    async def aclose(self):
        await self.http.aclose()

    # ------------------------------------------------------------------ STT
    async def transcribe(self, samples, user_token: Optional[str] = None) -> str:
        wav = pcm16_to_wav(samples, 16000)
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
        return text

    async def _stt_groq(self, wav: bytes, key: str) -> str:
        r = await self.http.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": ("speech.wav", wav, "audio/wav")},
            data={"model": self.cfg["stt"].get("groq_model", "whisper-large-v3-turbo"),
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
        for prov in llm["providers"]:
            key = os.getenv(prov.get("api_key_env", ""), "")
            if not key:
                continue
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
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
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
    async def synth(self, text: str, gender: str, rate: str = "") -> bytes:
        """text -> PCM s16 mono 48k. Trả b'' nếu lỗi."""
        text = clean_for_speech(text)
        if not text:
            return b""
        import edge_tts
        tts = self.cfg["tts"]
        voice = tts["voice_female"] if gender == "female" else tts["voice_male"]
        try:
            comm = edge_tts.Communicate(text, voice, rate=rate or tts.get("rate", "+0%"),
                                        pitch=tts.get("pitch", "+0Hz"))
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
