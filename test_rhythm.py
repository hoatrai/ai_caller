"""Test offline cho rhythm.py:  python test_rhythm.py"""
import random

import numpy as np

from rhythm import (SR, fade_edges, jitter_rate, normalize_numbers_vi, pause_after_ms, polish_chunk, read_int,
                    silence_pcm, trim_silence)


def check(got, want):
    assert got == want, f"\n  got : {got!r}\n  want: {want!r}"


def test_read_int():
    check(read_int(0), "không")
    check(read_int(5), "năm")
    check(read_int(10), "mười")
    check(read_int(15), "mười lăm")
    check(read_int(21), "hai mươi mốt")
    check(read_int(25), "hai mươi lăm")
    check(read_int(105), "một trăm lẻ năm")
    check(read_int(110), "một trăm mười")
    check(read_int(200), "hai trăm")
    check(read_int(2000), "hai nghìn")
    check(read_int(2005), "hai nghìn không trăm lẻ năm")
    check(read_int(2025), "hai nghìn không trăm hai mươi lăm")
    check(read_int(1500000), "một triệu năm trăm nghìn")


def test_normalize():
    check(normalize_numbers_vi("tối nay 8h30 nha"), "tối nay tám giờ rưỡi nha")
    check(normalize_numbers_vi("hẹn 20h nhé"), "hẹn hai mươi giờ nhé")
    check(normalize_numbers_vi("7:15 tối"), "bảy giờ mười lăm tối")
    check(normalize_numbers_vi("8h05"), "tám giờ lẻ năm")
    check(normalize_numbers_vi("quán ở q7"), "quán ở quận bảy")
    check(normalize_numbers_vi("đi 2 người"), "đi hai người")
    check(normalize_numbers_vi("khoảng 200k"), "khoảng hai trăm nghìn")
    check(normalize_numbers_vi("1,5tr"), "một phẩy năm triệu")
    check(normalize_numbers_vi("200.000 đồng"), "hai trăm nghìn đồng")
    check(normalize_numbers_vi("giảm 50%"), "giảm năm mươi phần trăm")
    check(normalize_numbers_vi("số 0909123456"), "số không chín không chín một hai ba bốn năm sáu")
    check(normalize_numbers_vi("Alô anh Hùng hả?"), "Alô anh Hùng hả?")        # không có số -> giữ nguyên
    assert not any(c.isdigit() for c in normalize_numbers_vi("8h30, q1, 3 người, 150k, 10%"))


def test_pause_order_and_range():
    rng = random.Random(1)
    mid = [pause_after_ms("em tính rủ mấy đứa", rng=rng) for _ in range(200)]
    comma = [pause_after_ms("thì cũng,", rng=rng) for _ in range(200)]
    dot = [pause_after_ms("ok luôn.", rng=rng) for _ in range(200)]
    ask = [pause_after_ms("anh rảnh không?", rng=rng) for _ in range(200)]
    dots = [pause_after_ms("tối nay...", rng=rng) for _ in range(200)]
    assert max(mid) <= 120 and min(mid) >= 60
    assert 140 <= min(comma) and max(comma) <= 260
    assert 320 <= min(dot) and max(dot) <= 520
    assert 380 <= min(ask) and max(ask) <= 600
    assert 450 <= min(dots) and max(dots) <= 750
    assert sum(mid) < sum(comma) < sum(dot) < sum(dots)
    assert pause_after_ms("ok.", scale=0.0) == 0
    assert len(set(dot)) > 20          # có nhiễu, không đều đều


def test_jitter_rate():
    rng = random.Random(2)
    vals = {jitter_rate("+6%", "anh khỏe không em nghe nè", rng) for _ in range(100)}
    assert len(vals) >= 3
    for v in vals:
        n = int(v.rstrip("%"))
        assert -8 <= n <= 22 and v.endswith("%")
    assert jitter_rate("", "x") == ""
    q = np.mean([int(jitter_rate("+6%", "anh rảnh không em nói nghe?", rng).rstrip("%")) for _ in range(400)])
    s = np.mean([int(jitter_rate("+6%", "ờ vậy hả", rng).rstrip("%")) for _ in range(400)])
    assert q < 6 < s                   # câu hỏi chậm hơn, câu ngắn nhanh hơn


def _tone(ms, amp=8000):
    t = np.arange(int(SR * ms / 1000)) / SR
    return (np.sin(2 * np.pi * 220 * t) * amp).astype(np.int16)


def test_trim_and_fade():
    sil = np.zeros(int(SR * 0.4), dtype=np.int16)
    voice = _tone(600)
    pcm = np.concatenate([sil, voice, sil]).tobytes()          # 0.4s lặng + 0.6s tiếng + 0.4s lặng
    out = trim_silence(pcm)
    dur = len(out) / 2 / SR
    assert 0.6 <= dur <= 0.72, dur                              # ~0.6s + 2*35ms
    assert trim_silence(np.zeros(SR, dtype=np.int16).tobytes()) == np.zeros(SR, dtype=np.int16).tobytes()   # toàn lặng -> giữ nguyên
    f = np.frombuffer(fade_edges(voice.tobytes()), dtype=np.int16)
    assert f[0] == 0 and f[-1] == 0 and int(np.abs(f[len(f) // 3: 2 * len(f) // 3]).max()) > 1000
    assert len(polish_chunk(pcm)) % 2 == 0
    assert len(silence_pcm(250)) == int(SR * 0.25) * 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
