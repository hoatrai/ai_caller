"""
Tìm và nghe thử giọng tiếng Việt trên Fish Audio (dùng model free s2.1-pro-free). Chạy trong thư mục ai_caller,
cần FISH_API_KEY trong .env (hoặc biến môi trường):

    venv/bin/python fish_voices.py list                    # liệt kê giọng tiếng Việt (id, tên, tag)
    venv/bin/python fish_voices.py list "nữ" "miền nam"    # lọc theo chữ trong tên/mô tả/tag
    venv/bin/python fish_voices.py test ID1 ID2 ...        # tạo file nghe thử cho từng giọng -> voice_samples/fish_<id>.wav

Nghe thử rồi bỏ id giọng ưng ý (nữ miền Nam) vào config.json: tts.fish_voices_female = ["id1", "id2", ...].
Trang giọng có dạng fish.audio/m/<id> — id chính là chuỗi cuối.
"""
import os
import sys
import wave
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API = "https://api.fish.audio"
TEXT = "Alo anh Hùng hả? Em nè. Em gọi hỏi anh tí, tối nay anh rảnh không? Em tính rủ mấy đứa đi quán nướng."


def headers():
    key = os.getenv("FISH_API_KEY")
    if not key:
        sys.exit("Thiếu FISH_API_KEY (tạo ở fish.audio -> API keys, rồi ghi vào .env).")
    return {"Authorization": f"Bearer {key}"}


def list_voices(filters):
    found = {}
    for page in range(1, 6):
        r = httpx.get(f"{API}/model", headers=headers(), timeout=30,
                      params={"language": "vi", "page_size": 50, "page_number": page, "sort_by": "score"})
        r.raise_for_status()
        data = r.json()
        for it in data.get("items", []):
            found[it["_id"]] = it
        if not data.get("has_more") and len(data.get("items", [])) < 50:
            break
    n = 0
    for it in found.values():
        blob = f'{it.get("title", "")} {it.get("description", "")} {" ".join(it.get("tags", []))}'.lower()
        if all(f.lower() in blob for f in filters):
            n += 1
            print(f'{it["_id"]}  {it.get("title", "")[:40]:40}  [{", ".join(it.get("tags", []))[:60]}]')
    print(f"\n{n} giọng.")


def test_voices(ids):
    out = Path("voice_samples")
    out.mkdir(exist_ok=True)
    for vid in ids:
        r = httpx.post(f"{API}/v1/tts", timeout=60,
                       headers={**headers(), "model": "s2.1-pro-free"},
                       json={"text": TEXT, "reference_id": vid, "format": "pcm", "sample_rate": 24000,
                             "latency": "balanced"})
        if r.status_code != 200:
            print(f"!! {vid}: HTTP {r.status_code} {r.text[:200]}")
            continue
        fn = out / f"fish_{vid[:8]}.wav"
        with wave.open(str(fn), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(r.content[: len(r.content) // 2 * 2])
        print("ok", fn)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "test"):
        sys.exit(__doc__)
    (list_voices if sys.argv[1] == "list" else test_voices)(sys.argv[2:])
