"""Dùng giọng VieNeu đã clone cho bot.
  venv/bin/python use_vieneu_voice.py female "mien tay 1"
  venv/bin/python use_vieneu_voice.py male "ten giong"
"""
import json, sys
if len(sys.argv) < 3 or sys.argv[1] not in ("female", "male"):
    sys.exit(__doc__)
gender, names = sys.argv[1], sys.argv[2:]
c = json.load(open("config.json", encoding="utf-8"))
t = c.setdefault("tts", {})
t["provider"] = "vieneu"
t[f"vieneu_voices_{gender}"] = names
json.dump(c, open("config.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("provider =", t["provider"], "|", f"vieneu_voices_{gender} =", names)
