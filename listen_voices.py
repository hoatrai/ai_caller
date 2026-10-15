"""
Tạo file .wav nghe thử từng giọng VieNeu (mặc định: 5 giọng nữ). Chạy trong thư mục ai_caller:

    venv/bin/python listen_voices.py                 # 5 giọng nữ -> thư mục voice_samples/
    venv/bin/python listen_voices.py "Ái Hân" "Mai Anh"   # chỉ vài giọng
    venv/bin/python listen_voices.py --all           # cả 11 giọng (nam + nữ)

Xong thì tải thư mục voice_samples/ về máy nghe (vd: scp -r root@server:~/ai_caller/voice_samples .).
Dùng đúng cấu hình bot đang chạy (steps=8, sway=-1, speed theo rate +6%).
"""
import sys
import time
import wave
from pathlib import Path

import numpy as np
from vieneu import Vieneu

TEXTS = [
    "Alo anh Hùng hả? Em nè.",
    "Dạ em gọi hỏi anh tí, tối nay anh rảnh không? Em tính rủ mấy đứa đi quán nướng.",
]
FEMALE_DEFAULT = ["Ái Hân", "Mỹ Duyên", "Xuân Tiên", "Mai Anh", "Trúc Ly"]


def save_wav(path: Path, x, sr: int):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    pcm = np.clip(x * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    eng = Vieneu(mode="v3nano", steps=8)
    voices = {name: label for label, name in eng.list_preset_voices()}
    print("Các giọng có sẵn:")
    for name, label in voices.items():
        print("  -", label)
    if "--all" in sys.argv:
        names = list(voices)
    else:
        names = args or FEMALE_DEFAULT
    out = Path("voice_samples")
    out.mkdir(exist_ok=True)
    for name in names:
        if name not in voices:
            print(f"!! Không có giọng '{name}' — bỏ qua")
            continue
        for i, text in enumerate(TEXTS, 1):
            t0 = time.perf_counter()
            wav = eng.infer(text, voice=name, speed=1.06, sway=-1.0)
            sr = int(eng.sample_rate)
            fn = out / f"{name.replace(' ', '_')}_{i}.wav"
            save_wav(fn, wav, sr)
            print(f"ok {fn}  ({time.perf_counter() - t0:.1f}s)")
    print("Xong. Tải thư mục", out.resolve(), "về máy để nghe.")


if __name__ == "__main__":
    main()
