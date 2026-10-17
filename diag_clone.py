import os, sys, wave, json, httpx
from dotenv import load_dotenv
load_dotenv("/root/ai_caller/.env")
KEY = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY")
VID = sys.argv[1]
H = {"Authorization": f"Bearer {KEY}"}
TEXT = "Alô anh hả? Em nè. Anh ăn cơm chưa nghen? Tối nay anh rảnh hông, qua nhà em chơi đi."

r = httpx.get(f"https://api.fish.audio/model/{VID}", headers=H, timeout=30)
print("GET model:", r.status_code)
if r.status_code == 200:
    j = r.json()
    for k in ("title", "state", "train_mode", "visibility", "languages", "type"):
        print(f"  {k}: {j.get(k)}")
    print("  samples:", len(j.get("samples") or []), "| tags:", j.get("tags"))
    print("  description:", (j.get("description") or "")[:150])
else:
    print(r.text[:300])

def tts(name, body, model="s2.1-pro-free"):
    rr = httpx.post("https://api.fish.audio/v1/tts", timeout=90,
                    headers={**H, "model": model},
                    json={"text": TEXT, "format": "pcm", "sample_rate": 24000, "latency": "normal", **body})
    print(name, rr.status_code, rr.text[:100] if rr.status_code != 200 else "")
    if rr.status_code == 200:
        with wave.open(f"voice_samples/diag_{name}.wav", "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(rr.content[: len(rr.content) // 2 * 2])

tts("clone", {"reference_id": VID})
tts("noref", {})
tts("clone_s2pro", {"reference_id": VID}, model="s2-pro")
