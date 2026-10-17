#!/usr/bin/env python3
"""Chốt CỨNG độ dài cho cuộc gọi bóng bàn (anvy <-> adminroot), đúng quy tắc "1-3 câu, dưới 40 từ".

Vì sao cần: log cho thấy anh Hùng nói 48 từ. Lý do là chốt cắt trong code đang rộng hơn prompt:
  - anh Hùng (vai người yêu): admin_reply_limits = 4 câu / 60 từ
  - bot anvy (vai thông minh): humanize_reply = 6 câu / 90 từ
Prompt bảo ngắn nhưng chốt cắt cho qua. Script này, CHỈ cho user trong PINGPONG_USERS (anvy):
  - anh Hùng: tối đa 2 câu / 30 từ
  - anvy:     tối đa 3 câu / 38 từ
  - cách cắt mới: giữ CÂU HỎI cuối (câu hỏi lật ngược thế cờ là linh hồn của bóng bàn), bỏ bớt câu đầu nếu quá dài;
    câu đơn quá dài thì cắt ở dấu phẩy gần nhất, không để lại ".?" như bản cũ.
Các vai khác (kieuthom, halinh, hanhtay...) giữ nguyên.

Chạy trong ~/ai_caller, SAU KHI đã chạy add_anvy_smart.py:
    python3 fix_pingpong_limit.py
    venv/bin/python -m py_compile brain.py autoadmin.py session.py && systemctl restart nhau-ai-caller
Tạo .bak_pplimit lần đầu. Sai mốc thì dừng, KHÔNG sửa gì. Chạy lại an toàn.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
MARK = "# --- PINGPONG LIMIT ---"
BOT_LIMIT = (3, 38)      # (số câu, số từ) cho anvy
ADMIN_LIMIT = (2, 30)    # (số câu, số từ) cho anh Hùng

LIMIT_FN = f'''{MARK}
def _limit_pp(text: str, max_sents: int, max_words: int) -> str:
    """Cắt cứng cho cuộc bóng bàn: giữ câu hỏi cuối (nếu có), thêm các câu đầu chừng nào còn vừa số từ/số câu."""
    sents = split_sentences(text)
    if len(sents) <= max_sents and len(text.split()) <= max_words:
        return text
    if not sents:
        return text
    tail = sents[-1] if (len(sents) > 1 and sents[-1].endswith("?")) else ""
    head = sents[:-1] if tail else sents
    budget = max_words - (len(tail.split()) if tail else 0)
    slots = max_sents - (1 if tail else 0)
    keep = []
    for s in head:
        w = len(s.split())
        if slots <= 0 or w > budget:
            break
        keep.append(s)
        budget -= w
        slots -= 1
    out = keep + ([tail] if tail else [])
    res = " ".join(out) if out else sents[0]
    words = res.split()
    if len(words) > max_words:      # một câu đơn quá dài: cắt ở dấu phẩy gần nhất trước giới hạn
        cut = " ".join(words[:max_words])
        k = cut.rfind(",")
        if k < len(cut) // 2:
            k = cut.rfind(" ")
        res = cut[:k].rstrip(" ,;.!?") + ("?" if res.rstrip().endswith("?") else ".")
    return res


'''

SESSION_NEW_IMPORT = "        from persona import PINGPONG_USERS as _PPU, SMART_TAG as _ST      # chốt cứng độ dài cho cuộc bóng bàn\n"


def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak_pplimit")
    if not b.exists():
        shutil.copy2(p, b)


def need(s: str, old: str, what: str):
    if s.count(old) != 1:
        sys.exit(f"[LỖI] không tìm thấy đúng 1 chỗ để vá: {what} -> KHÔNG sửa gì.")


def main():
    bp, ap, sp = ROOT / "brain.py", ROOT / "autoadmin.py", ROOT / "session.py"
    bs, as_, ss = (f.read_text(encoding="utf-8") for f in (bp, ap, sp))
    if "_PINGPONG_BLOCK" not in bs or "_PINGPONG_ADMIN" not in as_:
        sys.exit("[LỖI] chưa có add_anvy_smart.py. Chạy nó trước.")

    B1_OLD = "def limit_reply(text: str, max_sents: int = 2, max_words: int = 36) -> str:"
    B1_NEW = LIMIT_FN + "def limit_reply(text: str, max_sents: int = 2, max_words: int = 36, pp: bool = False) -> str:"
    B2_OLD = "    sents = split_sentences(text)\n    if len(sents) <= max_sents and len(text.split()) <= max_words:\n        return text\n    if len(sents) > 1:\n        tail = sents[-1] if"
    B2_NEW = ("    if pp:\n        return _limit_pp(text, max_sents, max_words)\n" + B2_OLD)
    B3_OLD = "_PINGPONG_BLOCK = ("
    B3_NEW = '_PP = {"on": False}      # cờ theo cuộc gọi: bật khi vai thông minh của user trong PINGPONG_USERS\n' + B3_OLD
    B4_OLD = "    if p.scenario_tag == SMART_TAG:\n        love_block = _SMART_BLOCK + ("
    B4_NEW = '    _PP["on"] = (p.scenario_tag == SMART_TAG and p.username.lower() in PINGPONG_USERS)      # đặt cờ mỗi lần dựng prompt, không rò sang cuộc sau\n' + B4_OLD
    B5_OLD = "    text = limit_reply(dedupe_a(text), max_sents=6, max_words=90) if smart else limit_reply(dedupe_a(text))"
    B5_NEW = (f"    text = (limit_reply(dedupe_a(text), max_sents={BOT_LIMIT[0]}, max_words={BOT_LIMIT[1]}, pp=True) if _PP[\"on\"] else\n"
              "            limit_reply(dedupe_a(text), max_sents=6, max_words=90)) if smart else limit_reply(dedupe_a(text))")

    A1_OLD = "def admin_reply_limits(rel: str) -> tuple[int, int]:"
    A1_NEW = "def admin_reply_limits(rel: str, p=None) -> tuple[int, int]:"
    A2_OLD = '    return (4, 60) if rel == "lover" else (2, 36)\n'
    A2_NEW = (f'    if p is not None and p.scenario_tag == SMART_TAG and p.username.lower() in PINGPONG_USERS:\n'
              f'        return {ADMIN_LIMIT}      # bóng bàn: anh Hùng nói gọn\n' + A2_OLD)

    S1_OLD = "        _ms, _mw = admin_reply_limits(rel)\n"
    S1_NEW = (SESSION_NEW_IMPORT + "        _ms, _mw = admin_reply_limits(rel, self.persona)\n"
              "        _pp = (self.persona.scenario_tag == _ST and self.persona.username.lower() in _PPU)\n")
    S2_OLD = "max_sents=_ms, max_words=_mw) if reply else"
    S2_NEW = "max_sents=_ms, max_words=_mw, pp=_pp) if reply else"

    d_b, d_a, d_s = MARK not in bs, "p=None" not in as_, "admin_reply_limits(rel, self.persona)" not in ss
    if d_b:
        for o, w in ((B1_OLD, "limit_reply def"), (B2_OLD, "limit_reply body"), (B3_OLD, "_PINGPONG_BLOCK"), (B4_OLD, "love_block smart"), (B5_OLD, "humanize_reply")):
            need(bs, o, w)
    if d_a:
        for o, w in ((A1_OLD, "admin_reply_limits def"), (A2_OLD, "admin_reply_limits body")):
            need(as_, o, w)
    if d_s:
        for o, w in ((S1_OLD, "session admin_reply_limits"), (S2_OLD, "session limit_reply call")):
            need(ss, o, w)

    if d_b:
        backup(bp)
        for o, n in ((B1_OLD, B1_NEW), (B2_OLD, B2_NEW), (B3_OLD, B3_NEW), (B4_OLD, B4_NEW), (B5_OLD, B5_NEW)):
            bs = bs.replace(o, n)
        bp.write_text(bs, encoding="utf-8")
        print("brain.py: đã vá")
    else:
        print("brain.py: đã vá trước đó, bỏ qua")
    if d_a:
        backup(ap)
        as_ = as_.replace(A1_OLD, A1_NEW).replace(A2_OLD, A2_NEW)
        ap.write_text(as_, encoding="utf-8")
        print("autoadmin.py: đã vá")
    else:
        print("autoadmin.py: đã vá trước đó, bỏ qua")
    if d_s:
        backup(sp)
        ss = ss.replace(S1_OLD, S1_NEW).replace(S2_OLD, S2_NEW)
        sp.write_text(ss, encoding="utf-8")
        print("session.py: đã vá")
    else:
        print("session.py: đã vá trước đó, bỏ qua")
    print("Tiếp theo: venv/bin/python -m py_compile brain.py autoadmin.py session.py && systemctl restart nhau-ai-caller")


if __name__ == "__main__":
    main()
