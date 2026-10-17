"""Chọn giọng nam miền Nam cho admin ảo (adminroot) và ghi vào config.json (tts.vieneu_voice_map).

Chạy trong thư mục /root/ai_caller:
    venv/bin/python pin_admin_voice.py                # chỉ liệt kê giọng nam + vùng, gợi ý giọng
    venv/bin/python pin_admin_voice.py --apply        # ghi giọng gợi ý vào config.json (có file .bak)
    venv/bin/python pin_admin_voice.py --apply --voice "Minh Quân"   # tự chọn giọng
"""
import argparse
import json
import shutil
import sys


def parse(label: str):
    # nhãn dạng "Minh Quân — Nam · Nam · Phong cách tự nhiên"
    desc = label.split("—", 1)[1].strip() if "—" in label else ""
    parts = [x.strip() for x in desc.split("·")]
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else ""), desc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--voice", default="")
    ap.add_argument("--key", default="adminroot")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    mode = cfg.get("tts", {}).get("vieneu_mode", "v3nano")
    from vieneu import Vieneu
    eng = Vieneu(mode=mode)
    rows = [(name, *parse(label)) for label, name in eng.list_preset_voices()]

    males = [(n, r, d) for n, g, r, d in rows if g == "Nam"]
    print(f"\n{len(males)} giọng nam trong VieNeu ({mode}):")
    for n, r, d in males:
        print(f"  {n:<14} vùng={r or '?':<8} {d}")

    south = [n for n, r, _ in males if r == "Nam"]
    pick = a.voice or (south[0] if south else "")
    if a.voice and a.voice not in [n for n, _, _ in males]:
        sys.exit(f"Không có giọng nam tên '{a.voice}'.")
    if not pick:
        print("\nKhông thấy giọng nam nào vùng Nam trong danh sách -> hãy chọn tay bằng --voice.")
        return
    print(f"\nGiọng gợi ý cho {a.key}: {pick}" + ("" if a.voice else f"  (các giọng nam miền Nam: {', '.join(south)})"))

    if a.apply:
        shutil.copy(a.config, a.config + ".bak")
        cfg.setdefault("tts", {}).setdefault("vieneu_voice_map", {})[a.key] = pick
        json.dump(cfg, open(a.config, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Đã ghi tts.vieneu_voice_map[{a.key!r}] = {pick!r} (bản cũ: {a.config}.bak)")
    else:
        print("Thêm --apply để ghi vào config.json.")


if __name__ == "__main__":
    main()
