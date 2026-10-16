"""Tạo giọng Fish từ audio mẫu (voice clone).
  venv/bin/python clone_voice.py "tên giọng" file1.wav [file2.wav ...] [--text "lời trong audio"]
Không có --text thì Fish tự nhận dạng lời (ASR)."""
import os, sys, httpx
from dotenv import load_dotenv
load_dotenv("/root/ai_caller/.env")
KEY = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY trong .env")

args = sys.argv[1:]
text = None
if "--text" in args:
    i = args.index("--text")
    text = args[i + 1]
    del args[i:i + 2]
if len(args) < 2:
    sys.exit(__doc__)
title, files = args[0], args[1:]

data = {"type": "tts", "title": title, "train_mode": "fast",
        "visibility": "private", "enhance_audio_quality": os.getenv("ENHANCE", "true")}
if text:
    data["texts"] = text
opened = [open(p, "rb") for p in files]
multipart = [("voices", (os.path.basename(p), f, "audio/mpeg" if p.lower().endswith(".mp3") else "audio/wav"))
             for p, f in zip(files, opened)]
try:
    r = httpx.post("https://api.fish.audio/model", headers={"Authorization": f"Bearer {KEY}"},
                   data=data, files=multipart, timeout=300)
finally:
    for f in opened:
        f.close()
print("HTTP", r.status_code)
try:
    j = r.json()
    print("id   :", j.get("_id"))
    print("state:", j.get("state"))
    if r.status_code >= 300:
        print(r.text[:500])
except Exception:
    print(r.text[:500])
