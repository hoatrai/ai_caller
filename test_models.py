import os, sys, wave, httpx
from dotenv import load_dotenv
load_dotenv("/root/ai_caller/.env")
KEY = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY")
VID = sys.argv[1] if len(sys.argv) > 1 else "6e713f3cd5c941f48dfe546c843f28fe"
TEXT = "Alô anh hả? Em nè. Anh ăn cơm chưa nghen? Tối nay anh rảnh hông, qua nhà em chơi đi, vô đây nè."
for model in ("s2.1-pro-free", "s1", "speech-1.6", "speech-1.5"):
    r = httpx.post("https://api.fish.audio/v1/tts", timeout=90,
        headers={"Authorization": f"Bearer {KEY}", "model": model},
        json={"text": TEXT, "reference_id": VID, "format": "pcm", "sample_rate": 24000, "latency": "normal"})
    print(model, r.status_code, r.text[:100] if r.status_code != 200 else "")
    if r.status_code == 200:
        with wave.open(f"voice_samples/model_{model}.wav", "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(r.content[: len(r.content) // 2 * 2])
