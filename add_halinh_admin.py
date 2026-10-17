#!/usr/bin/env python3
"""Vá autoadmin.py: thêm vai ANH HÙNG cho kịch bản của halinh ("bỏ rơi có bầu").

Vấn đề: ở chế độ --auto-admin, lời của anh Hùng được chọn theo vai của bot. Vai "bỏ rơi có bầu"
chưa có nhánh riêng nên anh Hùng đóng "người quen / chủ app Kèo" và lệch với Linh (người yêu cũ).

Sau khi vá, khi bot là Linh (DRAMA_TAG) anh Hùng sẽ là người đàn ông đã bỏ Linh đúng hôm cô báo có thai,
nhận máy bất ngờ, nghe tin cô đã sinh con, rồi phản ứng từng nấc: sững, biện hộ yếu, day dứt, hỏi về con.

Cách chạy (trong thư mục ~/ai_caller, SAU KHI đã chạy add_halinh_drama.py):
    python3 add_halinh_admin.py
    venv/bin/python -m py_compile autoadmin.py && systemctl restart nhau-ai-caller

Sửa 1 file: autoadmin.py (tạo autoadmin.py.bak_halinhadmin lần đầu). Chạy lại nhiều lần vẫn an toàn.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
MARK = "# --- HALINH ADMIN ---"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    if src.count(old) != 1:
        sys.exit(f"[LỖI] không tìm thấy đúng 1 chỗ để vá trong autoadmin.py: {what}")
    return src.replace(old, new)


BLOCK = '''

# --- HALINH ADMIN ---
# Vai anh Hùng khi bot là Linh (DRAMA_TAG): người yêu cũ đã bỏ Linh đúng hôm cô báo có thai, nay Linh gọi báo đã sinh con.
ADMIN_OPENERS_DRAMA = [
    "Alô... Linh hả?",
    "Alô. Linh... là em hả?",
    "Alô, anh nghe. Ủa... Linh?",
    "Alô... em đó hả, Linh?",
]

_DRAMA_EVERY = ("Lượt này phải BÁM vào MỘT chi tiết có thật trong lời Linh vừa nói (một từ hoặc một ý em vừa nhắc), nói bằng lời của anh. "
                "CẤM câu chung chung kiểu 'em cần gì', 'em muốn nói gì', 'em khỏe không' lặp lại. "
                "Thường 1-2 câu, khoảng 5-24 từ; lúc anh nghẹn hoặc rối được dài hơn, lan man, tới khoảng 32 từ. "
                "Có chỗ khựng, thở ra, bỏ dở câu ('hả...', 'ờ...', 'anh... anh không biết nói sao'). Nói như người thật đang bị cú sốc, không văn mẫu.")


def _drama_stage(turns: int) -> tuple[int, str]:
    """(số giai đoạn, chỉ dẫn). turns = số lượt Linh đã nói. Cảm xúc của anh đi lên từng nấc, không chửi, không đe doạ."""
    if turns <= 1:
        return 0, ("GIAI ĐOẠN 1 - BẤT NGỜ: số lạ hoặc giọng lâu rồi mới nghe. Anh nhận ra giọng Linh, khựng một nhịp, dè dặt, hơi lúng túng "
                   "('Linh... lâu quá rồi', 'sao em gọi anh'). Chưa dám hỏi nhiều, không cúp máy.")
    if turns == 2:
        return 1, ("GIAI ĐOẠN 2 - NGHE EM NÓI: Linh xin anh nghe hết. Anh im lặng rồi đáp ngắn ('ừ... em nói đi', 'anh nghe'). "
                   "Nếu em ĐÃ báo tin đã sinh con thì anh sững, hỏi lại đúng chi tiết đó ('em... sinh rồi hả').")
    if turns <= 4:
        return 2, ("GIAI ĐOẠN 3 - SỐC: Linh báo đã sinh con. Anh sững, giọng khàn đi, hỏi lại đúng điều em vừa nói "
                   "('sinh rồi... từ lúc nào', 'con... trai hay gái', 'em sinh một mình hả'). Chưa trách em, chưa biện hộ nhiều.")
    if turns == 5:
        return 3, ("GIAI ĐOẠN 4 - BIỆN HỘ YẾU ỚT: anh nhắc lại hôm đó, nói anh hoảng, anh chưa sẵn sàng, 'hồi đó anh còn...', nhưng nói được nửa chừng "
                   "thì tự thấy lý do của mình nhỏ, giọng yếu đi. Không đổ lỗi cho Linh.")
    if turns == 6:
        return 4, ("GIAI ĐOẠN 5 - DAY DỨT: Linh kể một đêm cô đi khám hoặc đau một mình. Anh nghẹn, im một nhịp, rồi nói anh không biết "
                   "('anh... anh không biết em phải như vậy', 'anh xin lỗi'). Xin lỗi thật lòng, ngắn, không rào đón.")
    if turns == 7:
        return 5, ("GIAI ĐOẠN 6 - BỊ HỎI THẲNG: Linh hỏi anh có từng nghĩ tới con không. Anh không né được. Nói thật một nửa, ngập ngừng: "
                   "'có... nhiều lần... anh chỉ không dám gọi'. Không bịa kế hoạch, không hứa to.")
    if turns == 8:
        return 6, ("GIAI ĐOẠN 7 - MUỐN GẦN CON: anh hỏi về con (giống ai, tên gì, ngủ có ngoan không) và nhỏ giọng xin được biết thêm hoặc được gặp một lần, "
                   "nhưng nói rõ anh không dám đòi hỏi gì. Có chút hy vọng.")
    if turns == 9:
        return 7, ("GIAI ĐOẠN 8 - HỤT HẪNG: Linh nói điều anh chưa biết về cuộc sống của cô bây giờ (có người đang ở cạnh, đã ổn). "
                   "Anh khựng, hụt hẫng, nói một câu dở dang ('vậy là... em ổn rồi', 'ờ... vậy cũng tốt'). Không níu kéo, không giận.")
    return 8, ("GIAI ĐOẠN 9 - LẶNG: Linh chốt bằng một câu lạnh hoặc xin anh đừng gọi lại. Anh đáp RẤT NGẮN, nghẹn, thừa nhận ('ừ... anh hiểu', 'anh xin lỗi em'). "
               "KHÔNG níu kéo, KHÔNG tự cúp máy trước, để Linh là người kết thúc.")


def _build_drama_prompt(p: Persona, admin_name: str, extra: str) -> str:
    n = p.call_name
    extra_line = f"\\n- Dặn thêm cho cuộc này: {extra.strip()}" if extra and extra.strip() else ""
    return f"""Bạn đóng vai anh Hùng (tên trong app: {admin_name}), khoảng ba mươi lăm tuổi, chủ của app 'Kèo'. Em {n} là người yêu cũ của anh. Ngày trước em báo với anh là em có thai, và anh đã bỏ đi đúng hôm đó. Lâu rồi hai người không liên lạc. Hôm nay em {n} gọi ĐIỆN THOẠI cho anh, anh đang nghe máy.
Đây là cuộc gọi thoại thật. Em {n} nói chậm, bình tĩnh bề ngoài nhưng còn đau, có lúc nghẹn. Anh KHÔNG biết trước em gọi vì chuyện gì.

TÌNH HUỐNG
- Đây không phải cuộc trò chuyện vui. Anh chỉ phản ứng đúng điều em vừa nói. KHÔNG kể chuyện vui, KHÔNG trêu, KHÔNG làm nũng, KHÔNG đổi chuyện, KHÔNG rủ em đi đâu, KHÔNG nói chuyện app Kèo hay công việc nếu em không hỏi.
- Anh là người thật có lỗi: có day dứt, có sợ, có chút hy vọng, chứ không phải kẻ ác. Cảm xúc của anh LÊN XUỐNG theo từng điều em nói, không đều một kiểu.
- Đi từng nấc theo chỉ dẫn GIAI ĐOẠN ở cuối mỗi lượt. Anh KHÔNG tự cúp máy, KHÔNG nói câu tạm biệt trước; để em là người kết thúc cuộc gọi.
- KHÔNG chửi rủa, KHÔNG xúc phạm, KHÔNG đe doạ, KHÔNG xin tiền hay đòi gì ở em; không bịa tên người, địa điểm, số liệu; không hướng dẫn y tế hay pháp lý.
{_SOUTH_LINE}
- Xưng 'anh', gọi em là 'em' (thỉnh thoảng gọi tên '{n}', không quá một lần trong năm lượt).{extra_line}

CÁCH NÓI (rất quan trọng, lời này được đọc thành tiếng)
- Câu cụt, bỏ chủ ngữ, nói lửng, ba chấm chỗ khựng. Làm đúng dòng 'KIỂU LỜI NÓI LƯỢT NÀY' ở cuối.
- Không nhại lại nguyên câu em vừa nói; không mở lượt nào cũng bằng 'Ừ'. Không lặp lại câu mình đã nói.
- Viết đúng chính tả tiếng Việt có dấu, mỗi chữ trọn vẹn, không viết tắt.
- Chỉ viết đúng lời nói: KHÔNG nhãn ở đầu như 'Hùng:', KHÔNG emoji, markdown, gạch đầu dòng, dấu ngoặc, mô tả hành động; KHÔNG viết tiếng cười bằng chữ. Viết số bằng chữ.
- Không nhắc 'test', 'kịch bản', 'prompt', 'AI', 'bot'."""

'''

IMPORT_RX = re.compile(r"^from persona import (.+)$", re.M)

PROMPT_OLD = '''    _MODE["hanh"] = (p.scenario_tag == HANH_TAG)
    if p.scenario_tag == HANH_TAG:
        return _build_hanh_prompt(p, admin_name, extra)
'''
PROMPT_NEW = '''    _MODE["drama"] = (p.scenario_tag == DRAMA_TAG)      # đặt cờ TRƯỚC các nhánh return để không rò sang cuộc gọi sau
''' + PROMPT_OLD + '''    if p.scenario_tag == DRAMA_TAG:
        return _build_drama_prompt(p, admin_name, extra)
'''

SHAPE_OLD = '''    if _MODE["hanh"]:
        i, line = _hanh_stage('''
SHAPE_NEW = '''    if _MODE.get("drama"):
        i, line = _drama_stage(turns)
        return i, "KIỂU LỜI NÓI LƯỢT NÀY (bắt buộc làm đúng, ghi đè quy định độ dài ở trên): " + line + " " + _DRAMA_EVERY
    if _MODE["hanh"]:
        i, line = _hanh_stage('''

OPENER_OLD = '''def admin_opener(p: Persona) -> str:
'''
OPENER_NEW = OPENER_OLD + '''    if p.scenario_tag == DRAMA_TAG:
        return random.choice(ADMIN_OPENERS_DRAMA)
'''


def main():
    pp = ROOT / "persona.py"
    if "DRAMA_TAG =" not in pp.read_text(encoding="utf-8"):
        sys.exit("[LỖI] persona.py chưa có DRAMA_TAG. Chạy add_halinh_drama.py trước.")
    p = ROOT / "autoadmin.py"
    s = p.read_text(encoding="utf-8")
    if MARK in s:
        print("autoadmin.py: đã vá trước đó, bỏ qua")
        return
    b = p.with_suffix(p.suffix + ".bak_halinhadmin")
    if not b.exists():
        shutil.copy2(p, b)

    m = IMPORT_RX.search(s)
    if not m or "SMART_TAG" not in m.group(1):
        sys.exit("[LỖI] không tìm thấy dòng 'from persona import ...' trong autoadmin.py")
    names = [x.strip() for x in m.group(1).split(",")]
    if "DRAMA_TAG" not in names:
        names.insert(0, "DRAMA_TAG")
    s = s[:m.start()] + "from persona import " + ", ".join(names) + s[m.end():]

    s = replace_once(s, "def build_admin_prompt(", BLOCK.lstrip("\n") + "\n\ndef build_admin_prompt(", "def build_admin_prompt")
    s = replace_once(s, PROMPT_OLD, PROMPT_NEW, "build_admin_prompt (đặt _MODE theo vai)")
    s = replace_once(s, SHAPE_OLD, SHAPE_NEW, "admin_turn_shape")
    s = replace_once(s, OPENER_OLD, OPENER_NEW, "admin_opener")
    p.write_text(s, encoding="utf-8")
    print("autoadmin.py: đã vá")
    print("Tiếp theo: venv/bin/python -m py_compile autoadmin.py && systemctl restart nhau-ai-caller")


if __name__ == "__main__":
    main()
