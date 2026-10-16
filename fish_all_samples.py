"""Tạo file nghe thử cho TẤT CẢ giọng tiếng Việt trên Fish -> voice_samples/.
Tên file: <gioitinh>_<tuoi>_<ten-khong-dau>_<8 ky tu id>.wav. Chạy lại được (bỏ qua file đã có)."""
import os, re, sys, time, wave, unicodedata
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()
API = "https://api.fish.audio"
KEY = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY trong .env")
H = {"Authorization": f"Bearer {KEY}"}
TEXT = "Alo anh Hùng hả? Em nè. Em gọi hỏi anh tí, tối nay anh rảnh không? Em tính rủ mấy đứa đi quán nướng."
OUT = Path("voice_samples")
OUT.mkdir(exist_ok=True)


def slug(s):
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return (s or "zh")[:28]


items = {}
for sort in ("score", "task_count", "created_at"):      # mỗi kiểu sort chỉ lật được tối đa ~1000 giọng
    for page in range(1, 201):
        r = httpx.get(f"{API}/model", headers=H, timeout=30,
                      params={"language": "vi", "page_size": 50, "page_number": page, "sort_by": sort})
        r.raise_for_status()
        got = r.json().get("items", [])
        for it in got:
            items[it["_id"]] = it
        if len(got) < 50:
            break
    print(f"sort={sort}: tổng {len(items)}", flush=True)
print(f"Tìm thấy {len(items)} giọng. Bắt đầu tạo file...", flush=True)

ok = fail = skip = 0
for n, (vid, it) in enumerate(items.items(), 1):
    tags = [t.lower() for t in it.get("tags", [])]
    g = "female" if "female" in tags else "male" if "male" in tags else "neutral"
    age = next((a for a in ("young", "middle-aged", "old") if a in tags), "na")
    fn = OUT / f"{g}_{age}_{slug(it.get('title', ''))}_{vid[:8]}.wav"
    if fn.exists():
        skip += 1
        continue
    for attempt in range(3):
        try:
            r = httpx.post(f"{API}/v1/tts", timeout=60, headers={**H, "model": "s2.1-pro-free"},
                           json={"text": TEXT, "reference_id": vid, "format": "pcm",
                                 "sample_rate": 24000, "latency": "balanced"})
        except Exception as e:
            print(f"[{n}] !! {vid[:8]} lỗi mạng {e!r}", flush=True)
            time.sleep(3)
            continue
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        break
    else:
        r = None
    if r is None or r.status_code != 200:
        fail += 1
        print(f"[{n}/{len(items)}] !! {vid[:8]} {it.get('title','')[:20]}: HTTP {getattr(r,'status_code','-')} {getattr(r,'text','')[:100]}", flush=True)
        if r is not None and r.status_code in (401, 402):
            sys.exit("Dừng: key sai/hết hạn mức.")
        continue
    with wave.open(str(fn), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(r.content[: len(r.content) // 2 * 2])
    ok += 1
    print(f"[{n}/{len(items)}] ok {fn.name}", flush=True)
    time.sleep(1.5)
print(f"XONG: {ok} ok, {fail} lỗi, {skip} đã có. Thư mục: {OUT.resolve()}")
