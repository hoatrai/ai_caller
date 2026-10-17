#!/usr/bin/env python3
"""Sửa 3 lỗi thấy trong log cuộc gọi halinh (auto-admin):

1. Anh Hùng chỉ nói được "… em..." / "… hông?":
   - Model mở lượt bằng dấu ba chấm, hàm limit_reply coi "…" là MỘT câu rồi cắt phần còn lại.
   - Vai halinh chưa được coi là 'lover' nên anh Hùng chạy chế độ thường (giới hạn 2 câu, không có chỉ dẫn từng giai đoạn).
   => relation_of coi DRAMA_TAG là 'lover' (chỉ để bật chế độ suy luận + chỉ dẫn giai đoạn + giới hạn rộng hơn;
      lời nhấc máy và prompt vẫn là riêng của halinh), và bỏ dấu ba chấm đứng đầu lượt.
2. Tiếng "xen giọng": đoạn "…" đứng một mình bị đọc thành một câu 1 ký tự bằng giọng khác. Hết khi bỏ "…" đầu lượt.
3. Linh nói "con ấy": thêm quy tắc từ ngữ về con vào brain.py (gọi 'con', 'bé', 'con mình'; cấm 'con ấy', 'đứa ấy').

Chạy trong ~/ai_caller, SAU KHI đã chạy add_halinh_drama.py và add_halinh_admin.py:
    python3 fix_halinh_v2.py
    venv/bin/python -m py_compile autoadmin.py brain.py && systemctl restart nhau-ai-caller

Tạo .bak_halinhfix2 cho autoadmin.py và brain.py lần đầu. Sai mốc thì dừng, KHÔNG sửa gì. Chạy lại an toàn.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
MARK_A = "# --- HALINH FIX2 ---"
MARK_B = "TỪ NGỮ VỀ CON"


def count_or_exit(s: str, old: str, what: str):
    if s.count(old) != 1:
        sys.exit(f"[LỖI] không tìm thấy đúng 1 chỗ để vá: {what} -> KHÔNG sửa gì.")


def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak_halinhfix2")
    if not b.exists():
        shutil.copy2(p, b)


# ---------------------------------------------------------------- autoadmin.py
REL_OLD = '''    if p.scenario_tag in ROMANTIC_TAGS and p.gender == "female":
        return "lover"'''
REL_NEW = f'''    {MARK_A}
    if p.scenario_tag == DRAMA_TAG:
        return "lover"             # chỉ để bật suy luận + chỉ dẫn giai đoạn + giới hạn lời rộng; prompt/lời mở máy vẫn riêng của halinh
    if p.scenario_tag in ROMANTIC_TAGS and p.gender == "female":
        return "lover"'''

COLLAPSE_OLD = '''    t = (text or "").strip()
    n = len(t)
'''
COLLAPSE_NEW = '''    t0 = (text or "").strip()
    t = t0
    if _MODE.get("drama"):      # chỉ vai halinh: limit_reply coi mỗi "…" là một câu nên cắt còn "… không?"; đổi ba chấm giữa câu thành dấu phẩy (TTS vẫn ngắt hơi)
        t = re.sub(r"^[\\s.…]+", "", t0).strip() or t0
        t = re.sub(r"\\s*(?:\\.{2,}|…)(?![.…])\\s*(?=\\S)", ", ", t)
        t = re.sub(r"\\s*,(?:\\s*,)+", ",", t)
    n = len(t)
'''

EVERY_OLD = "Thường 1-2 câu, khoảng 5-24 từ; lúc anh nghẹn hoặc rối được dài hơn, lan man, tới khoảng 32 từ. "
EVERY_NEW = ("MỖI lượt phải có ít nhất MỘT câu hoàn chỉnh có chữ (tối thiểu 4 từ). KHÔNG mở lượt bằng dấu ba chấm; "
             "ba chấm chỉ nằm GIỮA câu, tối đa một lần mỗi lượt. "
             "Thường 1-2 câu, khoảng 5-22 từ; lúc anh nghẹn hoặc rối được dài hơn, lan man, tới khoảng 30 từ. ")

# ---------------------------------------------------------------- brain.py
BRAIN_OLD = '    "\\nCHI TIẾT: được tự nhắc những chuyện nhỏ cho thật'
BRAIN_NEW = ('    "\\nTỪ NGỮ VỀ CON (bắt buộc): gọi đứa bé là \'con\', \'bé\', \'con mình\' hoặc \'con của em\' (theo giới tính ở Chi tiết CỐ ĐỊNH: con trai thì \'thằng nhỏ\', con gái thì \'con bé\'). "\n'
             '    "TUYỆT ĐỐI KHÔNG nói \'con ấy\', \'đứa ấy\', \'nó ấy\', \'cháu\', \'đứa trẻ\'; hạn chế chữ \'ấy\' nói chung vì đây là giọng miền Nam. Khi nói với anh Hùng thì con là con CỦA HAI NGƯỜI (\'con mình\'). "\n'
             '    "KHÔNG mở lượt bằng dấu ba chấm; mỗi lượt có ít nhất một câu hoàn chỉnh có chữ."\n'
             + BRAIN_OLD)


def patch_autoadmin():
    p = ROOT / "autoadmin.py"
    s = p.read_text(encoding="utf-8")
    if MARK_A in s:
        print("autoadmin.py: đã sửa trước đó, bỏ qua")
        return None
    if "# --- HALINH ADMIN ---" not in s:
        sys.exit("[LỖI] autoadmin.py chưa được vá bởi add_halinh_admin.py. Chạy file đó trước.")
    for old, what in ((REL_OLD, "relation_of"), (COLLAPSE_OLD, "collapse_repeat"), (EVERY_OLD, "_DRAMA_EVERY")):
        count_or_exit(s, old, what)
    s = s.replace(REL_OLD, REL_NEW).replace(COLLAPSE_OLD, COLLAPSE_NEW).replace(EVERY_OLD, EVERY_NEW)
    return p, s


def patch_brain():
    p = ROOT / "brain.py"
    s = p.read_text(encoding="utf-8")
    if MARK_B in s:
        print("brain.py: đã sửa trước đó, bỏ qua")
        return None
    if "_DRAMA_BLOCK" not in s:
        sys.exit("[LỖI] brain.py chưa có _DRAMA_BLOCK. Chạy add_halinh_drama.py trước.")
    count_or_exit(s, BRAIN_OLD, "dòng CHI TIẾT trong _DRAMA_BLOCK")
    return p, s.replace(BRAIN_OLD, BRAIN_NEW)


def main():
    todo = [x for x in (patch_autoadmin(), patch_brain()) if x]     # kiểm tra mốc cả hai file trước, rồi mới ghi
    for p, s in todo:
        backup(p)
        p.write_text(s, encoding="utf-8")
        print(f"{p.name}: đã sửa")
    if todo:
        print("Tiếp theo: venv/bin/python -m py_compile autoadmin.py brain.py && systemctl restart nhau-ai-caller")


if __name__ == "__main__":
    main()
