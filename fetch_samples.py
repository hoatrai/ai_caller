"""Tải mp3 sample có sẵn của từng giọng (từ voices_cache.json) -> voice_originals/.
  venv/bin/python fetch_samples.py 20     # thử 20 file
  venv/bin/python fetch_samples.py        # tải hết"""
import json, re, sys, unicodedata
from pathlib import Path
import httpx


def slug(s):
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return (re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "zh")[:28]


v = json.load(open("voices_cache.json", encoding="utf-8"))
out = Path("voice_originals")
out.mkdir(exist_ok=True)
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
n = 0
for vid, it in v.items():
    for s in it.get("samples", [])[:1]:
        url = s.get("audio")
        if not url:
            continue
        fn = out / f"{vid[:8]}_{slug(it.get('title',''))}.mp3"
        if fn.exists():
            continue
        try:
            r = httpx.get(url, timeout=30)
            if r.status_code == 200:
                fn.write_bytes(r.content)
                n += 1
                print("ok", fn.name, flush=True)
        except Exception as e:
            print("!!", vid[:8], e)
    if n >= limit:
        break
print("Xong", n, "file ->", out.resolve())
