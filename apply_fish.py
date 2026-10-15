import json
import os
import re
import shutil

import httpx
from dotenv import load_dotenv

load_dotenv(".env")
# Chu Trung/Nhat/Han/Nga/Thai trong ten giong = giong cua nguoi nuoc ngoai
FOREIGN = re.compile("[\u2e80-\u9fff\u0400-\u04ff\u0e00-\u0e7f\uac00-\ud7af]")
SKIP = [
    "Jessica", "Voz ", "Administrator", "Areum", "Sơn Tùng", "SonTungMTP",
    "Doraemon", "Teto", "blazblue", "the first test", "Dreadlord",
    "Conan", "Nobita", "Fizzarolli", "Cocoa", "Furby", "MVM", "gay",
    "Buồi", "DO NOT USE", "mr beast", "Sếp Thanh", "thui",
    "Học Tiếng Việt", "Vietnamese Girl Voice", "VIETKIEUMY", "Kể",
    "Thuyết Minh", "Quảng Cáo", "Jiao", "zhuangfa", "Rivers", "KATHY",
]
h = {"Authorization": "Bearer " + os.environ["FISH_API_KEY"]}
items = {}
for page in range(1, 6):
    r = httpx.get(
        "https://api.fish.audio/model",
        headers=h,
        timeout=30,
        params={"language": "vi", "page_size": 50,
                "page_number": page, "sort_by": "score"},
    )
    r.raise_for_status()
    d = r.json()
    for it in d.get("items", []):
        items[it["_id"]] = it
    if len(d.get("items", [])) < 50:
        break


def good(it):
    title = it.get("title", "")
    t = it.get("tags", [])
    langs = it.get("languages") or []
    if FOREIGN.search(title) or any(s in title for s in SKIP):
        return False
    if langs and set(langs) != {"vi"}:      # giong da ngu (vi+en/zh) hay lai
        return False
    if "character-voice" in t and "conversational" not in t:
        return False
    return "old" not in t


CUTE_TAGS = {"cute", "sweet", "young", "soft", "gentle", "cheerful", "friendly", "playful", "kawaii", "lovely"}
CUTE_WORDS = ["dễ thương", "de thuong", "cute", "ngọt", "dịu", "nhẹ nhàng", "kawaii", "teen", "baby"]


def cute(it):
    tags = {x.lower() for x in it.get("tags", [])}
    blob = (it.get("title", "") + " " + (it.get("description") or "")).lower()
    return bool(tags & CUTE_TAGS) or any(w in blob for w in CUTE_WORDS)


F, M = [], []
for vid, it in items.items():
    if not good(it):
        continue
    t = it.get("tags", [])
    if "female" in t:
        F.append(vid)
    elif "male" in t:
        M.append(vid)
FT = [v for v in F if cute(items[v])]
MT = [v for v in M if cute(items[v])]
print("Nu (uu tien):", ", ".join(items[v]["title"] for v in FT) or "(khong co)")
print("Nam (uu tien):", ", ".join(items[v]["title"] for v in MT) or "(khong co)")
print("Nu:", ", ".join(items[v]["title"] for v in F))
print("Nam:", ", ".join(items[v]["title"] for v in M))
shutil.copyfile("config.json", "config.json.bak")
c = json.load(open("config.json", encoding="utf-8"))
tts = c.setdefault("tts", {})
tts.update({
    "provider": "fish",
    "gemini_first_turn": False,
    "fish_model": "s2.1-pro-free",
    "fish_fallback": "vieneu",
    "fish_latency": "balanced",
    "fish_temperature": 0.6,
    "fish_timeout_seconds": 8,
    "fish_cooldown_seconds": 60,
    "fish_voices_female": F,
    "fish_voices_male": M,
    "fish_voices_female_top": FT,
    "fish_voices_male_top": MT,
    "fish_top_ratio": 0.8,
})
with open("config.json", "w", encoding="utf-8") as f:
    f.write(json.dumps(c, ensure_ascii=False, indent=2))
print("Xong:", len(F), "giong nu,", len(M), "giong nam")