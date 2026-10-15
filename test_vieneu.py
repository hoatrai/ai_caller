import asyncio, sys, types, time, logging
import numpy as np
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
from config import DEFAULTS, _merge
from brain import Brain

class Fake:
    sample_rate = 24000
    def __init__(self, delay=0.0): self.delay = delay; self.calls = []
    def list_preset_voices(self):
        return [("Adam — Nam · Nam · Giọng đọc tự nhiên","Adam"),("Ái Hân — Nữ · Nam · Phong cách tin tức","Ái Hân"),
                ("Trúc Ly — Nữ · Bắc · Phong cách tự nhiên","Trúc Ly"),("Mạnh Dũng — Nam · Bắc · Phong cách tự nhiên","Mạnh Dũng")]
    def infer(self, text, voice=None, speed=1.0, sway=0.0):
        self.calls.append((voice, speed)); time.sleep(self.delay)
        return (np.sin(np.arange(24000)/10)*0.3).astype(np.float32)

def install(delay=0.0, boom=False):
    fake = Fake(delay)
    def Vieneu(mode="v3nano", **kw):
        if boom: raise RuntimeError("no HF")
        return fake
    sys.modules["vieneu"] = types.SimpleNamespace(Vieneu=Vieneu)
    return fake

def mk(**tts):
    return Brain(_merge(DEFAULTS, {"tts": {"provider": "vieneu", **tts}}))

async def main():
    # 1) chạy bình thường: 48k int16, giọng đúng giới tính/vùng, speed từ rate
    f = install(); b = mk(vieneu_min_pool=1)   # ép lọc vùng như cũ để kiểm tra chọn giọng theo vùng
    pcm = await b.synth("Alo anh Hùng hả? Em nè.", "female", rate="+6%", region="Miền Bắc", voice_key="ngoc")
    assert len(pcm) == 48000*2*1, len(pcm); print("female voice", f.calls)
    assert f.calls[0][0] == "Trúc Ly" and abs(f.calls[0][1]-1.06) < 1e-9
    await b.synth("ok", "male", region="TP.HCM", voice_key="hung"); print("male voice", f.calls[-1])
    assert f.calls[-1][0] == "Adam"
    # 1b) kho giọng như v3nano thật (1 nữ Nam, 1 nam Nam): nhiều user phải ra nhiều giọng khác nhau
    b = mk(); await b._vieneu_ensure_loaded(5)
    picks = {b._vieneu_pick_voice("female", "TP.HCM", f"user{i}") for i in range(30)}
    assert len(picks) >= 2, picks; print("voices used", picks)
    # 2) model không tải được -> b"" từ VieNeu, synth lùi về edge (ở đây edge không có mạng nên trả b"" nhưng không văng lỗi)
    install(boom=True); b = mk()
    assert await b._synth_vieneu("x", "female") == b""; assert b._vieneu_block_until > time.monotonic()
    # 3) quá giờ -> nghỉ
    install(delay=1.5); b = mk(vieneu_timeout_seconds=0.5)
    assert await b._synth_vieneu("x", "female") == b""; assert b._vieneu_block_until > time.monotonic()
    # 4) chậm 2 câu liên tục -> câu vẫn ra tiếng, sau đó nghỉ
    install(delay=0.3); b = mk(vieneu_slow_seconds=0.1)
    assert await b._synth_vieneu("a", "female"); assert await b._synth_vieneu("b", "female")
    assert await b._synth_vieneu("c", "female") == b""
    # 5) câu song song xếp hàng
    f = install(); b = mk()
    r = await asyncio.gather(*[b._synth_vieneu(f"c{i}", "male") for i in range(3)]); assert all(r)
    # 6) first_turn: provider edge nhưng lượt đầu dùng VieNeu
    f = install(); b = Brain(_merge(DEFAULTS, {"tts": {"provider": "edge", "vieneu_first_turn": True}}))
    assert await b.synth("alo", "male", gemini=True); n = len(f.calls)
    b._vieneu_block_until = time.monotonic()+99
    await b.synth("tiếp", "male", gemini=False); assert len(f.calls) == n    # lượt sau không đụng VieNeu
    # 7) warmup + chọn giọng ghi đè từ config
    f = install(); b = mk(vieneu_voices_female=["Ái Hân"]); await b.warmup()
    assert f.calls, "warmup phải chạy thử"; assert b._vieneu_pick_voice("female","Miền Bắc","u") == "Ái Hân"
    # 8) chốt engine theo cuộc gọi
    f = install(); b = mk(); assert await b.choose_engine("female", "", "u") == "vieneu"
    f = install(delay=0.3); b = mk(vieneu_probe_max_seconds=0.1); assert await b.choose_engine("female", "", "u") == "edge"
    install(boom=True); b = mk(); assert await b.choose_engine("female", "", "u") == "edge"
    assert await Brain(_merge(DEFAULTS, {})).choose_engine() == ""          # provider edge -> cách cũ
    # locked: chậm/quá giờ vẫn không "nghỉ", không lùi engine khác
    install(delay=0.3); b = mk(vieneu_locked_timeout_seconds=0.1)
    assert await b.synth("x", "female", engine="vieneu") == b""; assert b._vieneu_block_until == 0.0
    f = install(delay=0.2); b = mk(vieneu_slow_seconds=0.05, vieneu_slow_limit=1)
    for _ in range(3): assert await b.synth("x", "female", engine="vieneu")
    assert b._vieneu_block_until == 0.0
    print("ALL OK")
asyncio.run(main())