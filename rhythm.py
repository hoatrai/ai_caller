"""
Nhịp nói tự nhiên cho bot gọi điện (không phụ thuộc aiortc/httpx, chỉ cần numpy).

Vì sao giọng nghe "máy":
  1. Mỗi đoạn TTS bị cắt rời, nối thẳng vào nhau: chỗ thì sát rạt, chỗ thì hở dài
     tuỳ tốc độ tổng hợp. Người thật ngắt hơi theo dấu câu.
  2. TTS (nhất là VieNeu) chừa 0.2-0.5s im lặng ở đầu/cuối mỗi đoạn -> khoảng hở không kiểm soát được.
  3. Mọi đoạn cùng một tốc độ -> đều đều như đọc bài.
  4. Số/giờ ("8h", "q7", "2 người") bị đọc sai hoặc đọc từng chữ số.

Mọi hàm ở đây đều thuần (pure) nên test được offline: xem test_rhythm.py.
"""
import random
import re

import numpy as np

SR = 48000

# ------------------------------------------------------------------ đọc số tiếng Việt
_D = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_under_100(n: int) -> str:
    if n < 10:
        return _D[n]
    if n == 10:
        return "mười"
    if n < 20:
        u = n - 10
        return "mười " + ("lăm" if u == 5 else _D[u])
    t, u = divmod(n, 10)
    s = _D[t] + " mươi"
    if u == 0:
        return s
    if u == 1:
        return s + " mốt"
    if u == 5:
        return s + " lăm"
    return s + " " + _D[u]


def _read_under_1000(n: int, pad: bool) -> str:
    """pad=True khi đứng sau hàng lớn hơn (nghìn/triệu): 2005 -> 'hai nghìn không trăm lẻ năm'."""
    h, r = divmod(n, 100)
    parts = []
    if h > 0:
        parts.append(_D[h] + " trăm")
    elif pad:
        parts.append("không trăm")
    if r > 0:
        if r < 10 and (h > 0 or pad):
            parts.append("lẻ " + _D[r])
        else:
            parts.append(_read_under_100(r))
    return " ".join(parts)


def read_int(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + read_int(-n)
    parts = []
    started = False
    for base, name in ((10 ** 9, "tỷ"), (10 ** 6, "triệu"), (10 ** 3, "nghìn")):
        q, n = divmod(n, base)
        if q:
            parts.append(_read_under_1000(q, pad=started) + " " + name)
            started = True
    if n:
        parts.append(_read_under_1000(n, pad=started))
    return " ".join(parts)


def _spell_digits(s: str) -> str:
    return " ".join(_D[int(c)] for c in s if c.isdigit())


def _plain_number(s: str) -> str:
    if len(s) > 1 and s.startswith("0"):          # 0909..., 05 -> đọc từng số
        return _spell_digits(s)
    if len(s) >= 9 or len(s) > 12:                 # số điện thoại / số quá dài -> đọc từng số
        return _spell_digits(s)
    return read_int(int(s))


_TIME = re.compile(r"\b(\d{1,2})\s?h(\d{2})?\b|\b(\d{1,2}):(\d{2})\b")
_THOUSAND_SEP = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")
_MONEY_K = re.compile(r"\b(\d+(?:,\d+)?)\s?[kK]\b")
_MONEY_TR = re.compile(r"\b(\d+(?:,\d+)?)\s?tr\b")
_QUAN = re.compile(r"\b[Qq]\.?\s?(\d{1,2})\b")
_PERCENT = re.compile(r"(\d+(?:,\d+)?)\s?%")
_DECIMAL = re.compile(r"\b(\d+),(\d{1,2})\b(?!\d)")
_INT = re.compile(r"\d+")


def _num_or_decimal(s: str) -> str:
    if "," in s:
        a, b = s.split(",", 1)
        return _plain_number(a) + " phẩy " + (_spell_digits(b) if b.startswith("0") else read_int(int(b)))
    return _plain_number(s)


def normalize_numbers_vi(text: str) -> str:
    """'tối nay 8h30, q7, 2 người, 200k' -> 'tối nay tám giờ rưỡi, quận bảy, hai người, hai trăm nghìn'."""
    if not text or not re.search(r"\d", text):
        return text
    t = text

    def _time(m):
        if m.group(1) is not None:
            h, mi = int(m.group(1)), m.group(2)
        else:
            h, mi = int(m.group(3)), m.group(4)
        s = read_int(h) + " giờ"
        if mi:
            mm = int(mi)
            if mm == 30:
                s += " rưỡi"
            elif 0 < mm < 10:
                s += " lẻ " + _D[mm]
            elif mm:
                s += " " + read_int(mm)
        return s

    t = _TIME.sub(_time, t)
    t = _THOUSAND_SEP.sub(lambda m: m.group(0).replace(".", ""), t)
    t = _MONEY_K.sub(lambda m: _num_or_decimal(m.group(1)) + " nghìn", t)
    t = _MONEY_TR.sub(lambda m: _num_or_decimal(m.group(1)) + " triệu", t)
    t = _QUAN.sub(lambda m: "quận " + read_int(int(m.group(1))), t)
    t = _PERCENT.sub(lambda m: _num_or_decimal(m.group(1)) + " phần trăm", t)
    t = _DECIMAL.sub(lambda m: _num_or_decimal(m.group(0)), t)
    t = _INT.sub(lambda m: _plain_number(m.group(0)), t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------ ngắt nghỉ & tốc độ
def pause_after_ms(chunk: str, scale: float = 1.0, rng=random) -> int:
    """Thời gian ngắt hơi SAU một đoạn, theo dấu câu cuối đoạn (+ nhiễu ngẫu nhiên cho khỏi đều đều)."""
    c = (chunk or "").rstrip()
    if c.endswith("…") or c.endswith("..."):
        lo, hi = 450, 750          # nói lửng / đang nghĩ
    elif c.endswith("?"):
        lo, hi = 380, 600
    elif c.endswith((".", "!")):
        lo, hi = 320, 520
    elif c.endswith((",", ";", ":")):
        lo, hi = 140, 260
    else:
        lo, hi = 60, 120           # đoạn bị cắt giữa mệnh đề vì quá dài
    return int(rng.uniform(lo, hi) * max(0.0, scale))


def jitter_rate(base: str, chunk: str = "", rng=random) -> str:
    """Biến thiên tốc độ nhẹ giữa các đoạn: câu hỏi chậm hơn một chút, câu rất ngắn nhanh hơn một chút."""
    m = re.match(r"^\s*([+-]?\d+)\s*%\s*$", base or "")
    if not m:
        return base
    v = int(m.group(1)) + rng.uniform(-3.0, 3.0)
    words = len((chunk or "").split())
    if (chunk or "").rstrip().endswith("?"):
        v -= 2
    if 0 < words <= 3:
        v += 2
    v = max(-8, min(22, round(v)))
    return f"{int(v):+d}%"


# ------------------------------------------------------------------ xử lý PCM s16 mono 48k
def silence_pcm(ms: int) -> bytes:
    return b"\x00\x00" * int(SR * max(0, ms) / 1000)


def trim_silence(pcm: bytes, keep_ms: int = 35, win_ms: int = 5, rel: float = 0.03, floor: float = 150.0) -> bytes:
    """Cắt khoảng lặng đầu/cuối do TTS chừa lại (giữ lại keep_ms để không cụt phụ âm)."""
    if not pcm or len(pcm) < 4:
        return pcm
    x = np.frombuffer(pcm, dtype=np.int16)
    w = max(1, int(SR * win_ms / 1000))
    n = len(x) // w
    if n < 2:
        return pcm
    fr = x[: n * w].astype(np.float32).reshape(n, w)
    rms = np.sqrt((fr ** 2).mean(axis=1))
    thr = max(floor, float(rms.max()) * rel)
    idx = np.where(rms > thr)[0]
    if idx.size == 0:
        return pcm
    keep = int(SR * keep_ms / 1000)
    a = max(0, int(idx[0]) * w - keep)
    b = min(len(x), (int(idx[-1]) + 1) * w + keep)
    return x[a:b].tobytes()


def fade_edges(pcm: bytes, ms: int = 8) -> bytes:
    """Vuốt đầu/cuối vài ms cho khỏi 'tách' khi nối các đoạn."""
    if not pcm or len(pcm) < 4:
        return pcm
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    k = min(int(SR * ms / 1000), len(x) // 2)
    if k < 2:
        return pcm
    ramp = np.linspace(0.0, 1.0, k, dtype=np.float32)
    x[:k] *= ramp
    x[-k:] *= ramp[::-1]
    return np.clip(x, -32768, 32767).astype(np.int16).tobytes()


def polish_chunk(pcm: bytes) -> bytes:
    return fade_edges(trim_silence(pcm))
