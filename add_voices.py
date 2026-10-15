"""
Thêm giọng mới cho VieNeu v3 Nano bằng cách "nhân bản" từ clip mẫu (voice cloning), rồi lưu lại
để bot (brain.py) tự thấy giọng mới — brain.py không cần sửa gì.

Cách dùng (trong thư mục ai_caller):

    1) Bỏ clip mẫu vào thư mục voice_refs/  (mỗi clip = 1 giọng, tên file = tên giọng, vd  Thùy Linh.wav)
    2) venv/bin/python add_voices.py voice_refs --gender Nữ --region Nam
       (nam: --gender Nam;  miền Bắc: --region Bắc;  đổi phong cách: --style "Phong cách tự nhiên")
    3) Nghe thử các file trong voice_samples/ rồi restart bot.

    venv/bin/python add_voices.py --list                 # xem các giọng đang có
    venv/bin/python add_voices.py --remove "Thùy Linh"   # xoá 1 giọng đã thêm
    venv/bin/python add_voices.py --restore              # trả về danh sách giọng gốc của VieNeu

Yêu cầu clip mẫu:
  - Một người nói, phòng yên tĩnh, không nhạc nền, không echo. 8-15 giây là đẹp (model dùng 5 giây đầu để lấy
    "phong cách" và cả clip (tối đa 30s) để lấy "chất giọng").
  - Nói TỰ NHIÊN như đang chat/gọi điện: giọng nhân bản sẽ mang đúng phong cách của clip. Muốn bot bớt "đọc tin tức"
    thì đừng thu kiểu đọc báo.
  - Định dạng wav/flac/mp3/m4a/ogg đều được.
  - CHỈ dùng giọng của người đã đồng ý cho anh dùng (chính anh, người quen đồng ý, hoặc dữ liệu giọng có giấy phép).
    Không nhân bản giọng người nổi tiếng hay người không biết.

Lần đầu clone, thư viện sẽ tải thêm 3 model nhỏ (speaker_encoder, codec_encoder, reference_encoder) từ Hugging Face.
"""
import argparse
import shutil
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import vieneu
from vieneu import Vieneu

AUDIO_EXT = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aac"}
DIRECT_EXT = {".wav", ".flac"}          # soundfile đọc thẳng được, còn lại đổi sang wav trước


def pkg_voices_file() -> Path:
    return Path(vieneu.__file__).parent / "assets" / "voices_v3_nano.json"


def to_wav(src: Path, tmpdir: Path) -> Path:
    """Đổi mp3/m4a/... sang wav mono 24k (dùng PyAV, đã có sẵn vì bot cần)."""
    import av
    out = tmpdir / (src.stem + ".wav")
    container = av.open(str(src))
    rs = av.AudioResampler(format="s16", layout="mono", rate=24000)
    chunks = []
    for frame in container.decode(audio=0):
        for f in rs.resample(frame):
            chunks.append(f.to_ndarray().reshape(-1))
    container.close()
    if not chunks:
        raise RuntimeError(f"không giải mã được {src.name}")
    pcm = np.concatenate(chunks).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm.tobytes())
    return out


def save_wav(path: Path, x, sr: int):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    pcm = np.clip(x * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description="Thêm/xoá giọng VieNeu v3 Nano")
    ap.add_argument("folder", nargs="?", default="voice_refs", help="thư mục chứa clip mẫu")
    ap.add_argument("--gender", default="Nữ", choices=["Nữ", "Nam"])
    ap.add_argument("--region", default="Nam", choices=["Nam", "Bắc", "Trung"])
    ap.add_argument("--style", default="Phong cách tự nhiên")
    ap.add_argument("--no-denoise", action="store_true", help="không lọc ồn clip mẫu")
    ap.add_argument("--overwrite", action="store_true", help="ghi đè nếu trùng tên giọng")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--remove", metavar="TÊN")
    ap.add_argument("--restore", action="store_true", help="khôi phục danh sách giọng gốc")
    args = ap.parse_args()

    target = pkg_voices_file()
    backup = Path("voices_v3_nano.orig.json")

    if args.restore:
        if not backup.exists():
            sys.exit("Không thấy voices_v3_nano.orig.json (chưa từng thêm giọng, hoặc đã xoá bản sao lưu).")
        shutil.copyfile(backup, target)
        print("Đã khôi phục danh sách giọng gốc ->", target)
        return

    if not backup.exists() and target.exists():           # sao lưu danh sách gốc đúng 1 lần
        shutil.copyfile(target, backup)
        print("Đã sao lưu danh sách giọng gốc ->", backup.resolve())

    eng = Vieneu(mode="v3nano", steps=8)
    voices = {name: label for label, name in eng.list_preset_voices()}

    if args.list:
        for label in voices.values():
            print(" -", label)
        return

    if args.remove:
        if args.remove not in voices:
            sys.exit(f"Không có giọng '{args.remove}'. Hiện có: {', '.join(voices)}")
        eng.remove_voice(args.remove, save=True)
        print(f"Đã xoá '{args.remove}'. Restart bot để áp dụng.")
        return

    folder = Path(args.folder)
    clips = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO_EXT) if folder.is_dir() else []
    if not clips:
        sys.exit(f"Không thấy clip nào trong '{folder}/'. Bỏ file wav/mp3/m4a vào đó rồi chạy lại.")

    desc = f"{args.gender} · {args.region} · {args.style}"
    gender_key = "female" if args.gender == "Nữ" else "male"
    out = Path("voice_samples")
    out.mkdir(exist_ok=True)
    sample_text = "Alo anh Hùng hả? Em nè. Em gọi hỏi anh tí, tối nay anh rảnh không?"
    added = []
    with tempfile.TemporaryDirectory() as td:
        for clip in clips:
            name = clip.stem.replace("_", " ").strip()
            if name in voices and not args.overwrite:
                print(f"!! '{name}' đã tồn tại — bỏ qua (thêm --overwrite để ghi đè)")
                continue
            try:
                src = clip if clip.suffix.lower() in DIRECT_EXT else to_wav(clip, Path(td))
                t0 = time.perf_counter()
                eng.add_voice(name, str(src), description=desc, gender=gender_key,
                              denoise=not args.no_denoise)
                wav = eng.infer(sample_text, voice=name, speed=1.06, sway=-1.0)
                fn = out / f"{name.replace(' ', '_')}_clone.wav"
                save_wav(fn, wav, int(eng.sample_rate))
                print(f"ok  {name}  [{desc}]  ({time.perf_counter() - t0:.1f}s)  nghe thử: {fn}")
                added.append(name)
            except Exception as e:
                print(f"!! {name}: lỗi {e!r}")

    if not added:
        sys.exit("Không thêm được giọng nào.")
    path = eng.save_voices()
    shutil.copyfile(path, "voices_v3_nano.backup.json")
    print(f"\nĐã lưu {len(added)} giọng mới vào {path}")
    print("(bản sao: voices_v3_nano.backup.json — chạy lại script này nếu sau này cập nhật thư viện vieneu làm mất giọng)")
    print("Nghe thử các file *_clone.wav trong voice_samples/, ưng thì restart bot là dùng được ngay.")


if __name__ == "__main__":
    main()
