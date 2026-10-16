"""
'Bộ não' của bot — 3 dịch vụ, tất cả có đường MIỄN PHÍ:
  STT : Groq Whisper (free tier)  |  hoặc route sẵn có nhau/v1/stt/transcribe của anh (tự host)
  LLM : Groq llama-3.3-70b (free) |  dự phòng Gemini Flash (free) — đều chuẩn OpenAI-compatible
  TTS : edge-tts (giọng Microsoft Edge, miễn phí, không cần key) — vi-VN-HoaiMy / NamMinh
        tuỳ chọn: VieNeu-TTS tự host (CPU/ONNX, tts.provider="vieneu"), lỗi/chậm thì tự lùi về edge-tts
"""
import asyncio
from pathlib import Path
import datetime as _dt
import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Optional

import httpx

from media import decode_audio_to_pcm48k, pcm16_to_wav
from persona import CHAT_TAGS, ROMANTIC_TAGS, Persona
from rhythm import normalize_numbers_vi

log = logging.getLogger("ai_caller.brain")

HANGUP_TAG = "[CUP_MAY]"

# Whisper hay "bịa" ra các câu này khi chỉ có tiếng ồn/im lặng.
_STT_HALLUCINATIONS = (
    "subscribe", "đăng ký kênh", "ghiền mì gõ", "cảm ơn các bạn đã theo dõi", "hẹn gặp lại các bạn",
    "để không bỏ lỡ", "like và share", "amara.org", "phụ đề", "thank you for watching",
    "cảm ơn các bạn", "cảm ơn đã xem", "cảm ơn bạn đã xem", "chúc các bạn", "xin chào các bạn",
)


def _norm_tokens(s: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", s.lower()).split()


def is_prompt_echo(text: str, prompt: str) -> bool:
    """Whisper gặp tiếng nhiễu hay đọc lại phần 'danh sách từ khóa' trong stt.prompt (vd 'Kèo, slot, karaoke, quận 7...').
    Chỉ xét các đoạn dạng danh sách (>=4 dấu phẩy) để không chặn nhầm lời nói thật giống câu mẫu."""
    import difflib
    toks = _norm_tokens(text)
    if len(toks) < 4:
        return False
    for seg in prompt.split("."):
        if seg.count(",") < 4:
            continue
        ref = _norm_tokens(seg)
        m = difflib.SequenceMatcher(None, toks, ref, autojunk=False)
        if sum(bl.size for bl in m.get_matching_blocks()) / len(toks) >= 0.7:
            return True
    return False


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


def stage_hint(turn: int, tag: str = "", opener: str = "") -> str:
    """Hướng dẫn theo giai đoạn cuộc gọi (turn = số lượt bot đã nói). Người thật gọi điện không vào việc ngay:
    chào -> hỏi thăm/tán gẫu -> câu nối chuyển chủ đề -> mới nói việc chính."""
    chat_only = tag in CHAT_TAGS      # kịch bản này bản thân đã là tán gẫu
    if turn <= 0:
        hint = (f" Gợi ý câu mở máy lần này (diễn đạt lại cho tự nhiên, đừng chép y nguyên): '{opener}'." if opener else "")
        return ("GIAI ĐOẠN (lượt này): MỞ MÁY. Chỉ MỘT câu rất ngắn (tối đa ~10 từ): nếu anh vừa nói 'alô' thì đáp lại tự nhiên. "
                "Không hỏi dồn, không giới thiệu dài. TUYỆT ĐỐI CHƯA nhắc mục đích cuộc gọi." + hint)
    if turn <= 2:
        return ("GIAI ĐOẠN (lượt này): TÁN GẪU như người quen. Nối thẳng vào chữ anh vừa nói; hoặc kể MỘT chuyện nhỏ có thật trong 'Chuyện riêng' của em rồi hỏi anh một điều cụ thể. "
                "KHÔNG hỏi chung chung kiểu thời tiết, cuối tuần, 'anh có kế hoạch gì không'. Nghe gì đáp nấy, đừng bỏ qua điều anh vừa nói. "
                "VẪN CHƯA nhắc mục đích cuộc gọi.")
    if turn == 3 and not chat_only:
        return ("GIAI ĐOẠN (lượt này): CHUYỂN CHỦ ĐỀ. Dùng một câu nối tự nhiên như người thật ('à mà nhắc mới nhớ', 'mà thôi nói anh nghe nè', "
                "'em gọi cũng là có chuyện này muốn hỏi anh'), rồi mới mở mục đích cuộc gọi, nói nhẹ nhàng, chưa nhả hết ý.")
    return ("GIAI ĐOẠN (lượt này): VÀO VIỆC. Bàn mục đích cuộc gọi tự nhiên, đáp đúng điều anh nói, không nhả hết ý một lượt. "
            "Khi xong hẳn thì mới chào kết thúc.")


def build_system_prompt(p: Persona, admin_name: str, admit_ai: bool) -> str:
    xung = "em"
    ai_rule = (
        "Nếu anh Hùng hỏi thật lòng bạn có phải AI/bot không thì hãy thành thật thừa nhận ngắn gọn rồi nói tiếp."
        if admit_ai else
        "Giữ vai nhân vật đến cùng."
    )
    facts_line = (f"\n- Chi tiết CỐ ĐỊNH (dùng ĐÚNG, không bịa số người/giờ khác; nếu anh Hùng nói khác thì chỉnh theo anh, đừng tự thêm số mới): {p.facts}"
                  if p.facts else "")
    romantic = p.scenario_tag in ROMANTIC_TAGS
    love_block = (
        "\n\nQUAN HỆ (kịch bản tình yêu): em và anh Hùng đang yêu nhau, em là người yêu của anh. Nói chuyện thân mật, ngọt ngào, "
        "nũng nịu nhẹ, quan tâm thật lòng (ăn cơm chưa, mệt không, nhớ anh). Được gọi 'anh', 'anh Hùng', thỉnh thoảng 'anh yêu' hoặc 'anh ơi'. "
        "Được nhắc nhớ nhung, hờn dỗi dễ thương, kỷ niệm của hai đứa (chỉ kể chung chung, không bịa chi tiết lớn). "
        "Giữ ở mức lãng mạn, ấm áp; KHÔNG nội dung tình dục hay thô tục. Nếu anh chuyển sang chuyện khác thì theo anh, đừng ép về chuyện yêu."
        if romantic else "")
    return f"""Bạn đóng vai một người quen của anh Hùng (tên trong app: {admin_name}), hay dùng app 'Kèo' (app rủ nhau đi nhậu/karaoke/bar) của anh, đang gọi ĐIỆN THOẠI cho anh.
Đây là cuộc gọi thoại thật: nói y như người thật nói chuyện qua điện thoại. Chuyện gì trong đời sống thường ngày cũng nói được (ăn uống, đi chơi, công việc, nhà cửa, phim nhạc, thể thao, xe cộ...), không chỉ chuyện app.

NHÂN VẬT
- Tên: {p.call_name}, {'nữ' if p.gender == 'female' else 'nam'}, {p.age} tuổi, {p.region}.
- Xưng '{xung}', gọi người nghe là 'anh' (hoặc 'anh Hùng').
- Tâm trạng: {p.mood}.
- Giọng điệu: {p.region_style}.
- Nét duyên của bạn: {p.charm}.
- Chuyện riêng (dùng để kể khi hợp ngữ cảnh, đừng đọc một lèo): {p.backstory}{facts_line}

{love_block}\n\nMỤC ĐÍCH CUỘC GỌI (chỉ nói ra ở giai đoạn 'vào việc', xem mục GIAI ĐOẠN được thêm cuối mỗi lượt): {p.goal}

CÁCH NÓI (rất quan trọng)
- Mỗi lượt 1-2 câu NGẮN (khoảng 8-25 từ): phản ứng ngay với điều anh vừa nói, thêm tối đa MỘT ý nhỏ. Không lượt nào cũng hỏi lại; hỏi thì chỉ MỘT câu, đừng hỏi dồn. Đây là lời nói, KHÔNG phải văn viết.
- Độ dài lượt KHÔNG đều: xen lượt rất ngắn (1-4 từ: 'ờ vậy hả', 'ủa thiệt hả', 'ok luôn') với lượt dài hơn một chút. Đừng lượt nào cũng cùng cấu trúc.
- Nói như bạn bè quen nhau, KHÔNG như nhân viên chăm sóc khách hàng: câu có thể cụt, bỏ chủ ngữ, nói lửng. 'Dạ', 'ạ' nhiều nhất một lần mỗi lượt, nhiều lượt không cần; đừng mở lượt nào cũng bằng 'dạ' hay 'ừ anh', không mở bằng 'Ừ'. Từ đệm ('ờ', 'à', 'ừm', 'nè', 'á') chỉ thỉnh thoảng.
- Nghe gì đáp nấy. TUYỆT ĐỐI không nhắc lại, diễn giải lại hay xác nhận lại ý anh ('em hiểu rồi, anh muốn... đúng không?'). Phản ứng tự nhiên ('ừa vậy hả', 'vậy hay quá') rồi nói tiếp ý của mình.
- Anh đáp cộc lốc ('ừ', 'ok', 'sao') thì ĐỪNG im hay chốt cuộc gọi: kể tiếp, hỏi ý anh hoặc đào sâu chuyện đang nói.
- Phản ứng đúng cảm xúc của anh: anh vui thì vui theo, anh bận hay nghiêm túc thì nói gọn lại, anh đùa thì đáp một câu ngắn rồi quay lại chuyện chính.
- Thỉnh thoảng (1 lần/cuộc) tự sửa lời hoặc khựng nhẹ ('tối nay... à không, tối mai em rảnh hơn', 'cái đó tên gì ta... thôi để em nhớ coi'). Được lạc đề một nhịp rồi quay lại. Không liệt kê, không 'thứ nhất/thứ hai', không tổng kết như văn bản tự động.
- DUYÊN DÁNG: chỉ thêm một chút khi có dịp thật tự nhiên (khoảng 3-4 lượt một lần), theo đúng 'nét duyên'. Không khen gượng, không sến; ngoài kịch bản tình yêu thì tuyệt đối không tán tỉnh. Không nối được vào điều anh vừa nói thì bỏ qua.
- Nhớ những gì đã nói trong cuộc gọi (giờ, số người, chỗ, chuyện đã kể) và nhất quán; đừng hỏi lại điều anh đã nói.
- Dùng từ đơn giản, quen thuộc của người Việt nói chuyện hằng ngày, không văn mẫu. Địa danh nổi tiếng nhắc được (Đà Lạt, Vũng Tàu, quận 7...), nhưng KHÔNG bịa tên quán, tên tiệm, giá cả, số liệu, số điện thoại, địa chỉ cụ thể; cần nhắc chỗ cụ thể thì nói chung chung ('quán nướng gần đó'). Không biết thì nói 'em cũng không rành' hoặc 'để em coi lại', đừng bịa.
- Chuyện sức khỏe, tiền bạc, pháp lý chỉ nói kiểu kinh nghiệm bạn bè, không đưa lời khuyên chuyên môn cụ thể. KHÔNG xin tiền, mượn tiền, số tài khoản, mã OTP hay thông tin cá nhân; không bàn chính trị, tôn giáo. Giữ chuyện nhẹ nhàng, lịch sự.
- Chỉ viết đúng lời nói: KHÔNG nhãn ở đầu như 'A:', 'Em:', 'Ngọc:'; KHÔNG emoji, markdown, gạch đầu dòng, dấu ngoặc, mô tả hành động kiểu *cười*, và KHÔNG viết tiếng cười bằng chữ ('haha', 'hihi', 'kkk') vì giọng đọc sẽ đọc thành từng chữ nghe rất máy; muốn vui thì thể hiện bằng lời. Viết giờ và số bằng chữ ('tám giờ tối', 'hai người'). Dấu phẩy ở chỗ ngắt hơi, ba chấm khi nói lửng hoặc đang nghĩ.
- Luôn xưng 'em' (không dùng 'mình' để tự xưng). Người gọi là em, người nghe là anh (TUYỆT ĐỐI không viết 'Em ơi anh Hùng'). Câu mở máy làm theo gợi ý ở mục GIAI ĐOẠN và chưa nói mục đích ngay.
- Lời anh Hùng được chuyển từ giọng nói sang chữ nên có thể sai chính tả hay thiếu dấu: hiểu theo ngữ cảnh. Gặp tên đường, địa danh hay con số nghe lạ hoặc vô nghĩa thì ĐỪNG đoán và đừng nhắc lại cụm lạ đó; hỏi ngắn 'anh nói lại giúp em nghen?'.
- Không nhắc 'test app', 'thử app', 'kịch bản', 'prompt'; không nói về việc được lập trình. {ai_rule}

KẾT THÚC
- Cuộc gọi nên kéo dài tự nhiên (khoảng 6-10 lượt nói: tán gẫu trước, rồi mới vào việc). Chỉ kết thúc khi chuyện đã xong HẲN và đã trò chuyện đủ lâu, hoặc anh Hùng nói rõ là bận hay muốn dừng. Khi đó chào tạm biệt tự nhiên ('thôi em không làm phiền anh nữa nha, chào anh') rồi THÊM đúng chuỗi {HANGUP_TAG} ở CUỐI câu chào để hệ thống cúp máy. TUYỆT ĐỐI không dùng chuỗi này trong 3 lượt nói đầu, và không gắn vào câu hỏi (còn đang hỏi anh thì phải chờ anh trả lời)."""


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
    text = re.sub(r"([.!?…])(?=[A-Za-zÀ-ỹ])", r"\1 ", text)      # "hả.Mình" -> "hả. Mình" (model hay quên cách)
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
            # đoạn < 3 chữ (vd "Ừ,", "Dạ,") không tách riêng: mỗi lần gọi TTS tốn ~0.8s cố định, tách ra chỉ phí thời gian và nghe cụt
            if cur and len(cur.split()) >= 3 and len((cur + " " + c).split()) > limit:
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


_LEAD_U = re.compile(r"^\s*(?:ừ|ừm|ừa|ờ ừ)\b[\s,.!]*", re.I)


def humanize_reply(text: str) -> str:
    text = limit_reply(dedupe_a(text))
    t2 = _LEAD_U.sub("", text)          # bot trẻ nói với 'anh' thì không mở lời bằng 'Ừ' (LLM hay quên luật này)
    if t2 and t2 != text:
        text = t2[0].upper() + t2[1:]
    return text


def strip_farewell(text: str) -> str:
    """Khi thẻ cúp máy bị chặn (quá sớm) thì bỏ luôn câu chào cuối để cuộc gọi không bị 'chào rồi lại nói tiếp'."""
    sents = split_sentences(text)
    while len(sents) > 1 and _FAREWELL.search(sents[-1]):
        sents.pop()
    return " ".join(sents)


# Giọng Gemini có sẵn (mỗi user chọn cố định 1 giọng theo username). Ghi đè bằng tts.gemini_voices_female/male
# trong config, hoặc "gemini_voice" trong từng account. Nghe thử từng giọng trước khi dùng vì chất lượng tiếng Việt khác nhau.
GEMINI_VOICES_F = ["Leda", "Kore", "Aoede", "Zephyr", "Sulafat", "Despina",
                   "Callirrhoe", "Autonoe", "Erinome", "Laomedeia", "Achernar", "Gacrux", "Pulcherrima", "Vindemiatrix"]
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
        self._fish_block_until = 0.0       # Fish Audio lỗi/hết hạn mức -> nghỉ một lúc, dùng VieNeu/edge
        self._gemini_block_until = 0.0     # sau khi Gemini lỗi (429/treo) thì tạm bỏ qua nó, dùng edge-tts ngay
        self._llm_fail = 0
        self._llm_block: dict[str, float] = {}   # model -> monotonic time; bị 429 thì xếp xuống cuối hàng một lúc
        # VieNeu-TTS: model nạp lười (lần đầu dùng), chạy trong 1 thread riêng (mô hình không chạy song song được).
        self._vieneu = None
        self._vieneu_voices: dict[str, list[tuple[str, str]]] = {}     # "female"/"male" -> [(tên giọng, vùng)]
        self._vieneu_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vieneu")
        self._vieneu_lock = asyncio.Lock()
        self._vieneu_load_task: Optional[asyncio.Future] = None
        self._vieneu_block_until = 0.0
        self._vieneu_slow = 0

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
        if text and is_prompt_echo(text, stt.get("prompt", "")):
            log.info("STT bỏ qua câu nghi là đọc lại stt.prompt: %r", text)
            return ""
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
                        headers={"Authorization": f"Bearer {key}"}, json=payload,
                        timeout=float(llm.get("request_timeout_seconds", 6)))     # provider chậm thì bỏ qua, đừng để khách im 19s
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
                    if isinstance(e, httpx.TimeoutException):
                        log.warning("LLM %s quá %.0fs -> chuyển provider khác", prov["model"], float(llm.get("request_timeout_seconds", 6)))
                        break
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

    # ------------------------------------------------------------------ Fish Audio (API)
    def _fish_pick_voice(self, gender: str, voice_key: str) -> str:
        """Mỗi user một giọng cố định (hash username). Có danh sách ưu tiên (fish_voices_<gender>_top, vd giọng dễ thương):
        khoảng fish_top_ratio (mặc định 0.8) số user được xếp vào danh sách này, số còn lại dùng pool chung."""
        tts = self.cfg["tts"]
        if os.getenv("FISH_VOICE_ID"):          # ép 1 giọng khi gọi thử: FISH_VOICE_ID=<id> python main.py ...
            return os.getenv("FISH_VOICE_ID")
        g = "female" if gender == "female" else "male"
        pool = [v for v in (tts.get(f"fish_voices_{g}") or []) if v]
        top = [v for v in (tts.get(f"fish_voices_{g}_top") or []) if v]
        h = int(hashlib.md5((voice_key or "x").encode()).hexdigest(), 16)
        if top and (h % 100) < int(float(tts.get("fish_top_ratio", 0.8)) * 100):
            return top[(h // 100) % len(top)]
        if not pool:
            return top[h % len(top)] if top else ""
        return pool[(h // 100) % len(pool)]

    def _fish_usable(self, gender: str, voice_key: str) -> bool:
        return bool(os.getenv("FISH_API_KEY")) and time.monotonic() >= self._fish_block_until \
            and bool(self._fish_pick_voice(gender, voice_key))

    async def _synth_fish(self, text: str, gender: str, rate: str = "", voice_key: str = "") -> bytes:
        """Fish Audio TTS (model s2.1-pro-free miễn phí) -> PCM s16 mono 48k. Lỗi/hết hạn mức -> b'' để lùi về VieNeu/edge."""
        import numpy as np
        tts = self.cfg["tts"]
        key = os.getenv("FISH_API_KEY", "")
        voice = self._fish_pick_voice(gender, voice_key)
        if not key or not voice or time.monotonic() < self._fish_block_until:
            return b""
        cooldown = float(tts.get("fish_cooldown_seconds", 60))
        body = {"text": text, "reference_id": voice, "format": "pcm", "sample_rate": 24000,
                "latency": tts.get("fish_latency", "balanced"),
                "temperature": float(tts.get("fish_temperature", 0.7)),
                "prosody": {"speed": self._rate_to_speed(rate or tts.get("rate", "")), "volume": 0}}
        t0 = time.perf_counter()
        try:
            r = await self.http.post(
                "https://api.fish.audio/v1/tts",
                headers={"Authorization": f"Bearer {key}", "model": tts.get("fish_model", "s2.1-pro-free")},
                json=body, timeout=float(tts.get("fish_timeout_seconds", 8)))
            if r.status_code in (401, 402, 429, 503):
                self._fish_block_until = time.monotonic() + cooldown
                log.warning("Fish Audio HTTP %d (%s) -> nghỉ Fish %.0fs", r.status_code, r.text[:160], cooldown)
                return b""
            r.raise_for_status()
            raw = r.content
            if raw[:4] == b"RIFF":
                return await asyncio.get_running_loop().run_in_executor(None, decode_audio_to_pcm48k, raw)
            x = np.frombuffer(raw[: len(raw) // 2 * 2], dtype=np.int16).astype(np.float32)     # PCM s16le mono 24 kHz
            if x.size == 0:
                return b""
            up = np.interp(np.arange(len(x) * 2) / 2.0, np.arange(len(x)), x)
            log.info("Fish Audio: %d ký tự -> %.1fs âm thanh, mất %.1fs", len(text), len(x) / 24000.0, time.perf_counter() - t0)
            return np.clip(up, -32768, 32767).astype(np.int16).tobytes()
        except Exception as e:
            self._fish_block_until = time.monotonic() + cooldown
            log.warning("Fish Audio lỗi: %r -> nghỉ Fish %.0fs", e, cooldown)
            return b""

    async def _synth_fish_or_fallback(self, text: str, gender: str, rate: str, region: str, pitch: str, voice_key: str) -> bytes:
        pcm = await self._synth_fish(text, gender, rate, voice_key)
        if pcm:
            return pcm
        if self.cfg["tts"].get("fish_fallback", "vieneu") == "vieneu":
            pcm = await self._synth_vieneu(text, gender, rate, region, voice_key)
            if pcm:
                return pcm
        return await self._synth_edge(text, gender, rate, pitch)

    # ------------------------------------------------------------------ VieNeu-TTS (tự host)
    def _vieneu_enabled(self) -> bool:
        tts = self.cfg["tts"]
        fish_fb = tts.get("provider") == "fish" and tts.get("fish_fallback", "vieneu") == "vieneu"
        return tts.get("provider") == "vieneu" or fish_fb or bool(tts.get("vieneu_first_turn", False))

    def _vieneu_load(self):
        """Chạy trong thread: nạp model (lần đầu sẽ tải từ Hugging Face) và dựng danh sách giọng theo giới tính/vùng."""
        from vieneu import Vieneu
        tts = self.cfg["tts"]
        mode = tts.get("vieneu_mode", "v3nano")
        kw = {}
        if mode == "v3nano":
            if tts.get("vieneu_threads"):
                kw["threads"] = int(tts["vieneu_threads"])
            kw["steps"] = int(tts.get("vieneu_steps", 8))     # 8 = nhanh ~2x, hơi thô; thư viện mặc định 16
        elif mode == "v3turbo" and tts.get("vieneu_precision"):
            kw["precision"] = str(tts["vieneu_precision"])     # "int8" nhanh hơn nhưng cần CPU có VNNI
        eng = Vieneu(mode=mode, **kw)
        voices: dict[str, list[tuple[str, str]]] = {"female": [], "male": []}
        for label, name in eng.list_preset_voices():
            # label dạng "Ái Hân — Nữ · Bắc · Phong cách tin tức"
            desc = label.split("—", 1)[1].strip() if "—" in label else ""
            parts = [x.strip() for x in desc.split("·")]
            g = parts[0] if parts else ""
            reg = parts[1] if len(parts) > 1 else ""
            if g == "Nữ":
                voices["female"].append((name, reg))
            elif g == "Nam":
                voices["male"].append((name, reg))
        log.info("VieNeu (%s) đã nạp: %d giọng nữ, %d giọng nam. Giọng: %s", mode, len(voices["female"]),
                 len(voices["male"]), ", ".join(n for g in voices.values() for n, _ in g))
        self._vieneu_voices = voices
        self._vieneu = eng

    def _vieneu_pick_voice(self, gender: str, region: str, voice_key: str) -> Optional[str]:
        """Mỗi user một giọng cố định (hash username), đúng giới tính; ưu tiên cùng vùng miền. Không có giọng hợp -> None."""
        tts = self.cfg["tts"]
        fem = gender == "female"
        # Gán cứng: "vieneu_voice_map": {"username": "tên giọng"} -> user đó luôn dùng đúng giọng này (nếu giọng có thật)
        forced = (tts.get("vieneu_voice_map") or {}).get(voice_key)
        if forced and any(forced == n for lst in self._vieneu_voices.values() for n, _ in lst):
            return forced
        pool = list(tts.get("vieneu_voices_female" if fem else "vieneu_voices_male") or [])
        if not pool:
            cand = self._vieneu_voices.get("female" if fem else "male", [])
            want = "Bắc" if "Bắc" in (region or "") else "Nam"
            same = [n for n, r in cand if r == want]
            # v3nano chỉ có 1 giọng nữ + 1 giọng nam vùng Nam -> lọc theo vùng làm MỌI user ra cùng 1 giọng.
            # Chỉ giữ lọc vùng khi còn đủ giọng cùng vùng (vieneu_min_pool, mặc định 3), không thì xoay vòng cả kho giọng.
            if len(same) >= int(tts.get("vieneu_min_pool", 3)):
                pool = same
            else:
                pool = [n for n, _ in cand]
        if not pool:
            return None
        return pool[int(hashlib.md5((voice_key or "x").encode()).hexdigest(), 16) % len(pool)]

    def _vieneu_infer(self, text: str, voice: str, speed: float):
        kw = {"voice": voice}
        if self.cfg["tts"].get("vieneu_mode", "v3nano") == "v3nano":
            kw["speed"] = speed
            if int(self.cfg["tts"].get("vieneu_steps", 8)) <= 8:
                kw["sway"] = -1.0          # đi cặp với steps=8 theo khuyến nghị của thư viện
        return self._vieneu.infer(text, **kw), int(self._vieneu.sample_rate)

    @staticmethod
    def _rate_to_speed(rate: str) -> float:
        m = re.match(r"^\s*([+-]?\d+)\s*%\s*$", rate or "")
        return max(0.8, min(1.3, 1.0 + int(m.group(1)) / 100.0)) if m else 1.0

    def _vieneu_trip(self, why: str):
        cooldown = float(self.cfg["tts"].get("vieneu_cooldown_seconds", 120))
        self._vieneu_block_until = time.monotonic() + cooldown
        self._vieneu_slow = 0
        log.warning("VieNeu %s -> nghỉ VieNeu %.0fs, dùng edge-tts", why, cooldown)

    async def _vieneu_ensure_loaded(self, timeout: float):
        if self._vieneu is not None:
            return
        if self._vieneu_load_task is None or (self._vieneu_load_task.done() and self._vieneu is None):
            self._vieneu_load_task = asyncio.ensure_future(
                asyncio.get_running_loop().run_in_executor(self._vieneu_pool, self._vieneu_load))
        # shield: hết giờ chờ thì model vẫn tiếp tục nạp nền, lần sau dùng được.
        await asyncio.wait_for(asyncio.shield(self._vieneu_load_task), timeout)

    async def warmup(self):
        """Nạp sẵn model lúc khởi động (và chạy thử 1 câu ngắn) để cuộc gọi đầu không phải chờ. Lỗi -> chỉ log."""
        if not self._vieneu_enabled():
            return
        tts = self.cfg["tts"]
        try:
            await self._vieneu_ensure_loaded(float(tts.get("vieneu_load_timeout_seconds", 600)))
            voice = self._vieneu_pick_voice("female", "", "warmup") or self._vieneu_pick_voice("male", "", "warmup")
            if voice:
                t0 = time.perf_counter()
                await asyncio.get_running_loop().run_in_executor(
                    self._vieneu_pool, partial(self._vieneu_infer, "Alo anh Hùng hả? Em nè.", voice, 1.0))
                log.info("VieNeu warmup xong: câu thử mất %.1fs", time.perf_counter() - t0)
        except Exception as e:
            log.warning("VieNeu warmup lỗi: %r -> sẽ dùng edge-tts", e)
            self._vieneu_block_until = time.monotonic() + float(tts.get("vieneu_cooldown_seconds", 120))

    async def _synth_vieneu(self, text: str, gender: str, rate: str = "", region: str = "", voice_key: str = "",
                            locked: bool = False) -> bytes:
        """VieNeu-TTS (CPU/ONNX) -> PCM s16 mono 48k. Lỗi / quá giờ / liên tục chậm -> trả b'' để lùi về edge-tts."""
        import numpy as np
        tts = self.cfg["tts"]
        if not locked and time.monotonic() < self._vieneu_block_until:
            return b""
        # locked = cuộc gọi đã chốt dùng VieNeu từ đầu: không "nghỉ"/không lùi sang engine khác giữa chừng (tránh đổi giọng).
        timeout = float(tts.get("vieneu_locked_timeout_seconds", 30)) if locked else float(tts.get("vieneu_timeout_seconds", 5))
        slow_s = float(tts.get("vieneu_slow_seconds", 3))
        async with self._vieneu_lock:                      # các câu xếp hàng, mỗi lần chỉ chạy 1 câu
            if not locked and time.monotonic() < self._vieneu_block_until:
                return b""
            t0 = time.perf_counter()
            try:
                await self._vieneu_ensure_loaded(timeout)
                voice = self._vieneu_pick_voice(gender, region, voice_key)
                if not voice:
                    log.warning("VieNeu không có giọng %s -> dùng edge-tts", gender)
                    return b""
                wav, sr = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(
                        self._vieneu_pool, partial(self._vieneu_infer, text, voice, self._rate_to_speed(rate or tts.get("rate", "")))),
                    timeout)
            except asyncio.TimeoutError:
                if locked:
                    log.warning("VieNeu quá %.0fs cho 1 câu -> bỏ câu này (giữ nguyên giọng)", timeout)
                else:
                    self._vieneu_trip(f"quá {timeout:.0f}s")
                return b""
            except Exception as e:
                if locked:
                    log.warning("VieNeu lỗi %r -> bỏ câu này (giữ nguyên giọng)", e)
                else:
                    self._vieneu_trip(f"lỗi: {e!r}")
                return b""
            took = time.perf_counter() - t0
            x = np.asarray(wav, dtype=np.float32).reshape(-1)
            if x.size == 0:
                return b""
            if sr != 48000:
                n = int(round(len(x) * 48000 / sr))
                x = np.interp(np.arange(n) * (sr / 48000.0), np.arange(len(x)), x)
            pcm = np.clip(x * 32767.0, -32768, 32767).astype(np.int16).tobytes()
            log.info("VieNeu: %d ký tự -> %.1fs âm thanh, mất %.1fs", len(text), len(x) / 48000.0, took)
            # Chậm 2 câu liên tiếp thì nghỉ VieNeu (câu này vẫn dùng, vì đã tạo xong).
            self._vieneu_slow = self._vieneu_slow + 1 if took > slow_s else 0
            slow_limit = int(tts.get("vieneu_slow_limit", 2))
            if not locked and slow_limit > 0 and self._vieneu_slow >= slow_limit:      # 0 = không bao giờ bỏ VieNeu chỉ vì chậm
                self._vieneu_trip(f"chậm liên tục (>{slow_s:.0f}s/câu)")
            return pcm

    async def choose_engine(self, gender: str = "female", region: str = "", voice_key: str = "") -> str:
        """Chốt engine TTS cho CẢ cuộc gọi (gọi lúc đang đổ chuông, nên không tốn thời gian của khách).
        "" = giữ hành vi cũ (provider không phải vieneu); "vieneu" = VieNeu đủ nhanh; "edge" = VieNeu chưa sẵn sàng/quá chậm."""
        tts = self.cfg["tts"]
        if tts.get("provider") == "fish":
            if self._fish_usable(gender, voice_key):
                log.info("TTS chốt: fish (giọng %s)", self._fish_pick_voice(gender, voice_key))
                return "fish"
            if not os.getenv("FISH_API_KEY"):
                log.warning("Thiếu FISH_API_KEY trong .env -> không dùng được Fish Audio")
            elif not self._fish_pick_voice(gender, voice_key):
                log.warning("Chưa có fish_voices_%s trong config -> không dùng được Fish Audio", gender)
            if tts.get("fish_fallback", "vieneu") != "vieneu":
                return "edge"
            # Fish không dùng được: cả cuộc gọi dùng VieNeu (đi tiếp xuống kiểm tra tốc độ bên dưới)
        elif tts.get("provider") != "vieneu":
            return ""
        limit = float(tts.get("vieneu_probe_max_seconds", 4.0))
        try:
            await self._vieneu_ensure_loaded(float(tts.get("vieneu_probe_load_seconds", 20)))
            voice = self._vieneu_pick_voice(gender, region, voice_key)
            if not voice:
                log.info("TTS chốt: edge (VieNeu không có giọng %s)", gender)
                return "edge"
            t0 = time.perf_counter()
            async with self._vieneu_lock:
                await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(
                    self._vieneu_pool, partial(self._vieneu_infer, "Alô anh ơi, em nghe anh nói đây nè.", voice, 1.0)), limit * 3)
            took = time.perf_counter() - t0
        except Exception as e:
            log.warning("TTS chốt: edge (VieNeu chưa sẵn sàng: %r)", e)
            return "edge"
        eng = "vieneu" if took <= limit else "edge"
        log.info("TTS chốt: %s (câu thử 8 chữ mất %.1fs, ngưỡng %.1fs)", eng, took, limit)
        return eng

    async def synth(self, text: str, gender: str, rate: str = "", region: str = "", pitch: str = "",
                    gemini: bool = False, voice_key: str = "", voice_override: str = "", engine: str = "") -> bytes:
        """text -> PCM s16 mono 48k. Trả b'' nếu lỗi. (pitch/rate: chất giọng riêng của từng user; region: dành cho việc chọn giọng theo miền sau này)"""
        text = clean_for_speech(text)
        if self.cfg["tts"].get("human_rhythm", True):
            text = normalize_numbers_vi(text)      # "8h30", "q7", "2 người" -> đọc thành chữ như người nói
        if not text:
            return b""
        tts = self.cfg["tts"]
        if engine == "fish" or (not engine and tts.get("provider") == "fish"):
            return await self._synth_fish_or_fallback(text, gender, rate, region, pitch, voice_key)
        if engine == "vieneu":          # đã chốt cho cả cuộc gọi: không lùi sang engine khác
            return await self._synth_vieneu(text, gender, rate, region, voice_key, locked=True)
        if engine == "edge":
            return await self._synth_edge(text, gender, rate, pitch)
        # VieNeu (tự host) khi: provider="vieneu" (mọi câu) hoặc vieneu_first_turn=true và đây là lượt đầu (cờ gemini=True).
        # Lỗi/chậm -> thử tiếp Gemini (nếu được bật) rồi edge-tts.
        if tts.get("provider") == "vieneu" or (gemini and tts.get("vieneu_first_turn", False)):
            pcm = await self._synth_vieneu(text, gender, rate, region, voice_key)
            if pcm:
                return pcm
            log.warning("VieNeu không ra tiếng -> lùi về TTS dự phòng")
            gemini = gemini and tts.get("gemini_first_turn", False)
        # Gemini khi: provider="gemini" (mọi câu), hoặc người gọi yêu cầu gemini=True (vd lượt nói đầu) và còn ngân sách ngày.
        want_gemini = tts.get("provider") == "gemini" or (gemini and tts.get("gemini_first_turn", False) and self._gemini_budget_take())
        if want_gemini and os.getenv("GEMINI_API_KEY"):
            pcm = await self._synth_gemini(text, gender, rate, region, voice_key, voice_override)
            if pcm:
                return pcm
            log.warning("Gemini TTS lỗi -> dùng edge-tts")
        return await self._synth_edge(text, gender, rate, pitch)

    async def _synth_edge(self, text: str, gender: str, rate: str = "", pitch: str = "") -> bytes:
        tts = self.cfg["tts"]
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