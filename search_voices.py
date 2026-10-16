"""Tìm giọng Fish (không phân biệt dấu/hoa thường) trong tên + mô tả + tag.
  venv/bin/python search_voices.py --refresh        # tải lại cache (3 kiểu sort)
  venv/bin/python search_voices.py nam bo           # khớp TẤT CẢ từ
  venv/bin/python search_voices.py --any sai gon saigon hcm   # khớp BẤT KỲ từ
  venv/bin/python search_voices.py --tags           # liệt kê các tag hay gặp
"""
import json, os, sys, unicodedata, collections
import httpx
from dotenv import load_dotenv
load_dotenv()
CACHE = "voices_cache.json"


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def fetch():
    H = {"Authorization": f"Bearer {os.getenv('FISH_API_KEY')}"}
    allv = {}
    for sort in ("score", "task_count", "created_at"):
        for page in range(1, 201):
            r = httpx.get("https://api.fish.audio/model", headers=H, timeout=30,
                          params={"language": "vi", "page_size": 50, "page_number": page, "sort_by": sort})
            r.raise_for_status()
            got = r.json().get("items", [])
            for it in got:
                allv[it["_id"]] = it
            if len(got) < 50:
                break
        print(f"{sort}: tổng {len(allv)}", flush=True)
    json.dump(allv, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return allv


args = sys.argv[1:]
if "--refresh" in args or not os.path.exists(CACHE):
    voices = fetch()
else:
    voices = json.load(open(CACHE, encoding="utf-8"))
args = [a for a in args if a != "--refresh"]

if "--tags" in args:
    c = collections.Counter(t for v in voices.values() for t in v.get("tags", []))
    for t, n in c.most_common(60):
        print(f"{n:5}  {t}")
    sys.exit()

mode_any = "--any" in args
words = [norm(a) for a in args if not a.startswith("--")]
if not words:
    sys.exit(__doc__)
n = 0
for vid, it in voices.items():
    blob = norm(f'{it.get("title","")} {it.get("description","")} {" ".join(it.get("tags", []))}')
    ok = any(w in blob for w in words) if mode_any else all(w in blob for w in words)
    if ok:
        n += 1
        print(f'{vid}  {it.get("title","")[:35]:35}  [{", ".join(it.get("tags", []))[:50]}]')
print(f"\n{n} / {len(voices)} giọng khớp.")
