import asyncio, math, random
import numpy as np
import session as S
from config import DEFAULTS, _merge
from persona import make_persona

SR = 48000
def tone(ms, lead=300, tail=300):
    n = int(SR*ms/1000); t = np.arange(n)/SR
    v = (np.sin(2*math.pi*300*t)*8000).astype(np.int16)
    z = lambda m: np.zeros(int(SR*m/1000), dtype=np.int16)
    return np.concatenate([z(lead), v, z(tail)]).tobytes()

class FB:
    def __init__(self, delay): self.delay = delay
    async def synth(self, text, *a, **k): return tone(500)
    async def reply(self, system, history):
        await asyncio.sleep(self.delay); return "ok"
    async def choose_engine(self, *a, **k): return ""

def mk(delay, human=True):
    cfg = _merge(DEFAULTS, {"ice_servers": [], "tts": {"human_rhythm": human}})
    p = make_persona({"username": "duonganh"}, "Dương Anh")
    s = S.CallSession(cfg, FB(delay), {"username":"duonganh","token":"x","user_id":7,"display_name":"Dương Anh","avatar":"","gender":None}, p, 1)
    async def nowait(*a, **k): return None
    s.voice.wait_done = nowait
    return s

async def main():
    text = "Ờ vậy hả. Tối nay anh rảnh không? Em tính rủ mấy đứa."
    for human in (False, True):
        s = mk(0, human)
        await s.say(text)
        print(f"human_rhythm={human}: {len(s.voice._buf)/2/SR:.2f}s audio trong bộ đệm")
    s_h = mk(0, True); await s_h.say(text); dur_h = len(s_h.voice._buf)/2/SR
    s_o = mk(0, False); await s_o.say(text); dur_o = len(s_o.voice._buf)/2/SR
    # 3 đoạn x 0.5s tiếng (+70ms giữ lại) + 2 lần ngắt hơi ~0.3-0.6s; bản cũ: 3 x 1.1s lặng thừa
    assert 1.9 < dur_h < 3.3, dur_h
    assert abs(dur_o - 3.3) < 0.05, dur_o

    random.random = lambda: 0.1
    s = mk(2.0); s.turns = 1; s._fillers = [b"\x01\x00" * 4800]
    r = await s._reply_with_filler("sys", []); 
    print("LLM chậm -> filler trong bộ đệm:", len(s.voice._buf) > 0, "| reply:", r)
    assert len(s.voice._buf) > 0 and r == "ok"
    s = mk(0.1); s.turns = 1; s._fillers = [b"\x01\x00" * 4800]
    await s._reply_with_filler("sys", [])
    print("LLM nhanh -> không filler:", len(s.voice._buf) == 0)
    assert len(s.voice._buf) == 0
    s = mk(2.0); s.turns = 0; s._fillers = [b"\x01\x00" * 4800]
    await s._reply_with_filler("sys", [])
    assert len(s.voice._buf) == 0         # lượt mở máy không đệm
    print("OK")
asyncio.run(main())
