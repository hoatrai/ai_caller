"""Ghi TẤT CẢ giọng tiếng Việt trên Fish vào config.json (fish_voices_female / fish_voices_male).
Giữ nguyên fish_voices_*_top. Giọng tag 'neutral' bị bỏ qua (không rõ nam/nữ).
Dùng:  venv/bin/python fish_sync_all.py            # chỉ ghi pool
       venv/bin/python fish_sync_all.py --use-all  # ghi pool + fish_top_ratio=0 (bot chọn ngẫu nhiên trong TOÀN BỘ pool)"""
import json, os, shutil, sys
import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY trong .env")
H = {"Authorization": f"Bearer {KEY}"}
items = {}
for page in range(1, 201):
    r = httpx.get("https://api.fish.audio/model", headers=H, timeout=30,
                  params={"language": "vi", "page_size": 50, "page_number": page, "sort_by": "score"})
    r.raise_for_status()
    got = r.json().get("items", [])
    for it in got:
        items[it["_id"]] = it
    print(f"trang {page}: {len(items)} giọng", flush=True)
    if len(got) < 50:
        break

F = [v for v, it in items.items() if "female" in it.get("tags", [])]
M = [v for v, it in items.items() if "male" in it.get("tags", []) and "female" not in it.get("tags", [])]
shutil.copyfile("config.json", "config.json.before_all")
c = json.load(open("config.json", encoding="utf-8"))
t = c.setdefault("tts", {})
t["fish_voices_female"] = F
t["fish_voices_male"] = M
if "--use-all" in sys.argv:
    t["fish_top_ratio"] = 0.0
json.dump(c, open("config.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Xong: {len(F)} nữ, {len(M)} nam (bỏ {len(items) - len(F) - len(M)} giọng neutral). Bản cũ: config.json.before_all")
print("fish_top_ratio =", t.get("fish_top_ratio"))
