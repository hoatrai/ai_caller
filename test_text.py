import os, sys, wave, httpx
from dotenv import load_dotenv
load_dotenv("/root/ai_caller/.env")
KEY = os.getenv("FISH_API_KEY") or sys.exit("Thiếu FISH_API_KEY trong .env")
VID = sys.argv[1] if len(sys.argv) > 1 else "71bfcfbcbd664cb9a7c9dc1698601451"
TEXTS = {
    "chuan": "Alo anh hả? Em nè. Anh ăn cơm chưa? Tối nay anh có rảnh không, qua nhà em chơi đi.",
    "nam":   "Alo anh hả? Em nè. Anh ăn cơm chưa dzậy? Tối nay anh có rảnh hông, qua nhà em chơi đi, vô đây nè.",
    "tay":   "Alô anh hả? Em nè. Anh ăn cơm chưa dzậy ta? Tối nay anh rảnh hông, qua nhà em chơi đi nghen, dữ hôn.",
}
for name, text in TEXTS.items():
    r = httpx.post("https://api.fish.audio/v1/tts", timeout=60,
        headers={"Authorization": f"Bearer {KEY}", "model": "s2.1-pro-free"},
        json={"text": text, "reference_id": VID, "format": "pcm", "sample_rate": 24000, "latency": "balanced"})
    print(name, r.status_code, r.text[:120] if r.status_code != 200 else "")
    if r.status_code == 200:
        with wave.open(f"voice_samples/test_text_{name}.wav", "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(r.content[: len(r.content) // 2 * 2])
