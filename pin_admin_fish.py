"""Gán giọng Fish (theo 8 ký tự đầu của id, lấy từ tên file trong voice_samples/) cho adminroot.
Chạy trong /root/ai_caller:
    venv/bin/python pin_admin_fish.py f7dd07c1            # tra id đầy đủ, chỉ in ra
    venv/bin/python pin_admin_fish.py f7dd07c1 --apply    # ghi vào config.json -> tts.fish_voice_map["adminroot"] (có .bak)
Chấp nhận luôn cả tên file: pin_admin_fish.py voice_samples/male_..._f7dd07c1.wav --apply"""
import argparse, json, os, re, shutil, sys
import httpx
from dotenv import load_dotenv

load_dotenv()
ap = argparse.ArgumentParser()
ap.add_argument("ref")
ap.add_argument("--config", default="config.json")
ap.add_argument("--key", default="adminroot")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()

m = re.search(r"([0-9a-f]{8})(?:\.wav)?$", os.path.basename(a.ref).lower()) or re.fullmatch(r"[0-9a-f]{8,32}", a.ref.lower())
prefix = (m.group(1) if m and m.groups() else a.ref).lower()[:32]
cfg = json.load(open(a.config, encoding="utf-8"))
full = ""
for k in ("fish_voices_male", "fish_voices_female", "fish_voices_male_top", "fish_voices_female_top"):
    full = full or next((v for v in cfg.get("tts", {}).get(k, []) if v.startswith(prefix)), "")
if not full:
    key = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY trong .env")
    H = {"Authorization": f"Bearer {key}"}
    for sort in ("score", "task_count", "created_at"):
        for page in range(1, 201):
            r = httpx.get("https://api.fish.audio/model", headers=H, timeout=30,
                          params={"language": "vi", "page_size": 50, "page_number": page, "sort_by": sort})
            r.raise_for_status()
            items = r.json().get("items", [])
            full = next((it["_id"] for it in items if it["_id"].startswith(prefix)), "")
            if full or len(items) < 50:
                break
        if full:
            break
if not full:
    sys.exit(f"Không tìm thấy giọng Fish nào có id bắt đầu bằng {prefix}")
print("id đầy đủ:", full)
if a.apply:
    shutil.copy(a.config, a.config + ".bak")
    cfg.setdefault("tts", {}).setdefault("fish_voice_map", {})[a.key] = full
    json.dump(cfg, open(a.config, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Đã ghi tts.fish_voice_map[{a.key!r}] (bản cũ: {a.config}.bak)")
else:
    print("Thêm --apply để ghi vào config.json.")
