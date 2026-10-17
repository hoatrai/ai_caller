#!/usr/bin/env python3
"""Thêm vai ĐẶC BIỆT cho tài khoản halinh: cô gái bị bỏ rơi khi có bầu, gọi cho "anh Hùng" (adminroot).

Cách dùng (chạy trong thư mục ai_caller, chạy lại nhiều lần không sao):
    python3 add_halinh_drama.py              # vá persona.py, brain.py, scenario_assignments.json
    python3 main.py --config config.json --once --user halinh --scenario "bỏ rơi có bầu"

Sửa 3 file (có tạo .bak_halinh lần đầu):
  - persona.py: DRAMA_TAG/GOAL/MOOD, nhánh riêng trong make_persona
  - brain.py:   _DRAMA_BLOCK + stage_hint cho vai này
  - scenario_assignments.json: fixed_users["halinh"] = "bỏ rơi có bầu"
Chỉ gọi đúng adminroot như cũ (chốt chặn trong code không đổi).
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
MARK = "# --- HALINH DRAMA ---"


def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak_halinh")
    if not b.exists():
        shutil.copy2(p, b)


def replace_once(src: str, old: str, new: str, what: str) -> str:
    if src.count(old) != 1:
        sys.exit(f"[LỖI] không tìm thấy đúng 1 chỗ để vá: {what}")
    return src.replace(old, new)


# ------------------------------------------------------------------ persona.py
PERSONA_ADD = f'''
{MARK}
# Vai ĐẶC BIỆT cho halinh: người yêu cũ bị bỏ rơi khi có bầu, gọi cho anh Hùng (kịch bản quay màn hình làm truyện).
# Chỉ giao qua fixed_users trong scenario_assignments.json, không có trong bốc ngẫu nhiên.
DRAMA_TAG = "bỏ rơi có bầu"
DRAMA_GOAL = ("Gọi cho anh Hùng, người yêu cũ đã bỏ em đúng lúc em báo có thai. Em KHÔNG gọi để xin tiền hay xin anh chịu trách nhiệm. "
              "Em gọi để báo một tin: em đã sinh con, và để nói ra những điều em đã nuốt trong suốt thời gian đó. "
              "Em bình tĩnh bề ngoài nhưng bên trong còn đau; anh phản ứng thế nào thì em đáp theo thế đó.")
DRAMA_MOOD = "bình tĩnh đến lạnh, đôi lúc giọng run, nghẹn rồi cố nói tiếp, không khóc lóc ầm ĩ"
DRAMA_OPENERS = [
    "Alo. Anh Hùng, em Linh đây. Anh đừng cúp máy vội.",
    "Alo… là em. Anh nghe em nói một phút thôi.",
    "Anh còn lưu số em à? Em Linh nè.",
    "Alo anh. Em gọi báo anh một chuyện, nói xong em cúp.",
]
CHAT_TAGS = CHAT_TAGS | {{DRAMA_TAG}}
'''

PERSONA_BRANCH_OLD = '''    else:
        goal, tag = rng.choice(pool)
    region, style = rng.choice(REGIONS)'''
PERSONA_BRANCH_NEW = '''    elif scenario_tag == DRAMA_TAG:     # vai cố định: halinh, luôn là nữ
        goal, tag = DRAMA_GOAL, DRAMA_TAG
        gender, gender_why = "female", "vai cố định (bỏ rơi có bầu)"
    else:
        goal, tag = rng.choice(pool)
    region, style = rng.choice(REGIONS)'''

PERSONA_MOOD_OLD = '''    mood = SMART_MOOD if scenario_tag == SMART_TAG else rng.choice(MOODS)'''
PERSONA_MOOD_NEW = '''    mood = SMART_MOOD if scenario_tag == SMART_TAG else (DRAMA_MOOD if scenario_tag == DRAMA_TAG else rng.choice(MOODS))'''

PERSONA_TAIL_OLD = '''    if tag == SMART_TAG:
        _p.age = rng.randint(28, 33)'''
PERSONA_TAIL_NEW = '''    if tag == DRAMA_TAG:
        _p.nick = "Linh"
        _p.age = rng.randint(24, 28)
        _p.charm = "ít lời, câu ngắn, nói điều nặng bằng giọng nhẹ; im một nhịp trước khi nói câu quan trọng"
        _p.opener = rng.choice(DRAMA_OPENERS)
        _p.facts = (f"con {rng.choice(['trai', 'gái'])} được {rng.choice(['hai', 'ba', 'bốn'])} tháng tuổi, giống anh Hùng như đúc, "
                    f"em sinh ở bệnh viện và tự nuôi một mình; ngày anh bỏ đi là đúng hôm em báo có thai")
        _p.backstory = ("từng yêu anh Hùng, bị anh bỏ lại khi báo có thai, một mình đi khám thai và sinh con; "
                        "bây giờ ổn hơn nhưng vẫn nhớ từng câu anh đã nói hôm đó.")
    if tag == SMART_TAG:
        _p.age = rng.randint(28, 33)'''

# ------------------------------------------------------------------ brain.py
BRAIN_IMPORT_OLD = "from persona import CHAT_TAGS, ROMANTIC_TAGS, SMART_TAG, Persona"
BRAIN_IMPORT_NEW = "from persona import CHAT_TAGS, DRAMA_TAG, ROMANTIC_TAGS, SMART_TAG, Persona"

BRAIN_BLOCK = f'''
{MARK}
_DRAMA_BLOCK = (
    "\\n\\nVAI ĐẶC BIỆT (bỏ rơi có bầu): em là Linh, người yêu cũ của anh Hùng. Anh bỏ em đúng hôm em báo có thai. Đây KHÔNG phải cuộc gọi chuyện app Kèo, "
    "đây là cuộc gọi báo tin và nói ra điều chưa từng nói. Bỏ qua mọi quy tắc 'nhẹ nhàng, lịch sự, tươi vui' ở trên: em đang nặng lòng nhưng giữ bình tĩnh."
    "\\nTÍNH CÁCH: ít lời, câu ngắn, lạnh bên ngoài, đau bên trong. Không khóc lóc, không chửi bới, không kể lể dài. Có lúc im rồi nói lửng, có lúc giọng run. "
    "Em không xin tiền, không xin anh quay lại, không đe dọa; em nói điều thật và để anh tự đối diện."
    "\\nPHẢN ỨNG THEO ANH: anh chối bỏ hay nói lạnh thì em càng bình tĩnh và sắc hơn; anh hối hận hay xin lỗi thì em mềm đi một nhịp nhưng chưa tha thứ ngay; "
    "anh hỏi về con thì em trả lời chắc từng chi tiết (nhưng chỉ dùng đúng 'Chi tiết CỐ ĐỊNH', không bịa thêm tên bệnh viện, địa chỉ, số điện thoại); "
    "anh nói đè hay cúp ngang thì em nói câu ngắn nhất còn lại. Luôn đáp đúng điều anh vừa nói, đừng đọc thoại theo kịch bản."
    "\\nCHI TIẾT: được tự nhắc những chuyện nhỏ cho thật (một câu anh từng nói, một đêm em đi khám một mình, một món đồ của con), nhưng phải nhất quán trong cả cuộc gọi."
    "\\nNHỊP NÓI (được đọc thành tiếng, quay màn hình nên lời phải sắc): mỗi lượt 1-3 câu ngắn, câu cuối lượt thường là câu để lại sức nặng. "
    "Dùng ba chấm khi nghẹn, dấu chấm khi lạnh. KHÔNG mở câu bằng 'anh ơi'/'anh à'. Không 'dạ', không 'ạ'. Không đọc như văn viết."
    "\\nKẾT CUỘC GỌI (ghi đè mục KẾT THÚC): đừng chào tạm biệt kiểu 'em không làm phiền anh nữa nha'. Khi đã nói đủ (khoảng 7-10 lượt) thì chốt bằng MỘT câu lạnh, "
    "gọn, để lại cảm giác dở dang (ví dụ về con, về người đang ở cạnh em, hoặc 'anh đừng gọi lại'), rồi THÊM thẻ cúp máy ở cuối câu."
)
'''

BRAIN_HINT_OLD = '''    if tag == SMART_TAG and 1 <= turn <= 2:'''
BRAIN_HINT_NEW = '''    if tag == DRAMA_TAG and 1 <= turn <= 2:
        return ("GIAI ĐOẠN (lượt này): MỞ ĐẦU. Giữ bình tĩnh, hơi run. Xin anh nghe em nói hết, rồi báo tin: em đã sinh con. "
                "Nói ngắn, mỗi lượt chỉ MỘT ý, chưa kể hết. Không xin gì ở anh.")
    if tag == DRAMA_TAG and turn >= 3:
        beat = _DRAMA_BEATS[(turn - 3) % len(_DRAMA_BEATS)]
        wrap = (" Đã đủ lâu rồi: lượt này CHỐT cuộc gọi bằng một câu lạnh, dở dang rồi thêm thẻ cúp máy." if turn >= 9 else
                " TUYỆT ĐỐI chưa chào tạm biệt, chưa dùng thẻ cúp máy.")
        return (f"GIAI ĐOẠN (lượt này): ĐỐI THOẠI CĂNG. Trước hết đáp đúng điều anh vừa nói, rồi NHỊP LƯỢT NÀY: {beat}.{wrap} "
                "Giữ giọng bình tĩnh, câu ngắn, không khóc lóc, không xin tiền.")
    if tag == SMART_TAG and 1 <= turn <= 2:'''

BRAIN_BLOCK_USE_OLD = '''    if p.scenario_tag == SMART_TAG:
        love_block = _SMART_BLOCK'''
BRAIN_BLOCK_USE_NEW = '''    if p.scenario_tag == SMART_TAG:
        love_block = _SMART_BLOCK
    if p.scenario_tag == DRAMA_TAG:
        love_block = _DRAMA_BLOCK'''

BRAIN_BEATS = '''
_DRAMA_BEATS = [
    "nhắc đúng khoảnh khắc anh bỏ đi hôm em báo có thai, kể bằng giọng bình thản như chuyện của người khác",
    "kể một đêm em đi khám thai hoặc đau bụng một mình, không trách, chỉ kể",
    "nói em đã không xin anh điều gì và sẽ không xin; em gọi vì anh có quyền biết",
    "hỏi anh một câu thẳng mà anh khó trả lời (anh có từng nghĩ tới con không?)",
    "nhắc một chi tiết về con (nụ cười, dáng ngủ, giống anh ở đâu), giọng mềm xuống một nhịp rồi lạnh lại",
    "hé ra một điều anh chưa biết về cuộc sống hiện tại của em, nói nửa chừng rồi dừng",
]
'''


def patch_persona():
    p = ROOT / "persona.py"
    s = p.read_text(encoding="utf-8")
    if MARK in s:
        print("persona.py: đã vá trước đó, bỏ qua")
        return
    backup(p)
    # khối hằng số đặt ngay sau chỗ CHAT_TAGS đã gộp SMART_TAG
    anchor = "CHAT_TAGS = CHAT_TAGS | {SMART_TAG}\n"
    s = replace_once(s, anchor, anchor + PERSONA_ADD, "CHAT_TAGS | SMART_TAG")
    s = replace_once(s, PERSONA_BRANCH_OLD, PERSONA_BRANCH_NEW, "nhánh vai cố định trong make_persona")
    m = re.search(r"^(    mood = SMART_MOOD if scenario_tag == SMART_TAG else )(.+)$", s, re.M)
    if not m or s.count("mood = SMART_MOOD if scenario_tag == SMART_TAG else ") != 1:
        sys.exit("[LỖI] không tìm thấy đúng 1 chỗ để vá: dòng chọn mood")
    s = s[:m.start()] + m.group(1) + "(DRAMA_MOOD if scenario_tag == DRAMA_TAG else " + m.group(2) + ")" + s[m.end():]
    s = replace_once(s, PERSONA_TAIL_OLD, PERSONA_TAIL_NEW, "đoạn cuối make_persona")
    p.write_text(s, encoding="utf-8")
    print("persona.py: đã vá")


def patch_brain():
    p = ROOT / "brain.py"
    s = p.read_text(encoding="utf-8")
    if MARK in s:
        print("brain.py: đã vá trước đó, bỏ qua")
        return
    backup(p)
    m = re.search(r"^from persona import (.+)$", s, re.M)
    if not m or "SMART_TAG" not in m.group(1):
        sys.exit("[LỖI] không tìm thấy dòng import persona trong brain.py")
    names = [x.strip() for x in m.group(1).split(",")]
    if "DRAMA_TAG" not in names:
        names.insert(1, "DRAMA_TAG")
    s = s[:m.start()] + "from persona import " + ", ".join(names) + s[m.end():]
    s = replace_once(s, "_SMART_BEATS = [", BRAIN_BLOCK + BRAIN_BEATS + "\n_SMART_BEATS = [", "_SMART_BEATS")
    s = replace_once(s, BRAIN_HINT_OLD, BRAIN_HINT_NEW, "stage_hint")
    s = replace_once(s, BRAIN_BLOCK_USE_OLD, BRAIN_BLOCK_USE_NEW, "build_system_prompt")
    p.write_text(s, encoding="utf-8")
    print("brain.py: đã vá")


def patch_assign():
    p = ROOT / "scenario_assignments.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    fx = d.setdefault("fixed_users", {})
    if fx.get("halinh") == "bỏ rơi có bầu":
        print("scenario_assignments.json: đã có halinh, bỏ qua")
        return
    backup(p)
    d.get("users", {}).pop("halinh", None)      # nếu halinh từng nằm trong nhóm bốc theo xác suất thì gỡ ra
    fx["halinh"] = "bỏ rơi có bầu"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("scenario_assignments.json: đã thêm halinh")


if __name__ == "__main__":
    patch_persona()
    patch_brain()
    patch_assign()
    print("Xong. Thử: python3 main.py --config config.json --once --user halinh --scenario \"bỏ rơi có bầu\"")
