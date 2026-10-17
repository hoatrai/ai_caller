#!/usr/bin/env python3
"""anvy (CON GÁI) gọi adminroot theo công thức "2 AI tán tỉnh có nhịp bóng bàn".

Hai phía theo đúng bài hướng dẫn:
  - AI B = anvy: tinh tế, sắc sảo, ban đầu hơi giữ khoảng cách, bắt bài lại, thỉnh thoảng "thách" anh.
  - AI A = anh Hùng (adminroot): hóm hỉnh, chủ động thả thính, ẩn dụ nhẹ đời thường, hay đặt câu hỏi "bẫy".
Ràng buộc cho CẢ HAI: 1-3 câu (dưới 40 từ), cấm xác nhận kiểu "đúng vậy / em hiểu rồi / câu hỏi hay đấy",
mỗi lượt phải có (a) trêu/thả thính nhẹ hoặc (b) quan điểm ngược bất ngờ hoặc (c) câu hỏi lật ngược thế cờ,
và không kết lượt bằng sự đồng ý hoàn toàn.

Dựa trên vai có sẵn "người yêu thông minh" (như kieuthom) nhưng CHỈ bật các quy tắc bóng bàn cho user trong
PINGPONG_USERS (persona.py), nên kieuthom và các vai khác giữ nguyên. Muốn thêm user: sửa PINGPONG_USERS.

Cách chạy (trong ~/ai_caller):
    python3 add_anvy_smart.py
    venv/bin/python -m py_compile persona.py brain.py autoadmin.py && systemctl restart nhau-ai-caller
    venv/bin/python main.py --config config.json --once --user anvy --scenario "người yêu thông minh"

Sửa 5 file (tạo .bak_anvysmart lần đầu): persona.py, brain.py, autoadmin.py, scenario_assignments.json
(fixed_users["anvy"] = "người yêu thông minh", thay cho vai "bỏ rơi có bầu" nếu đã gán), config.json
(giọng NAM "Anh Khôi" của anvy -> giọng nữ). Sai mốc thì dừng, KHÔNG sửa gì. Chạy lại nhiều lần an toàn.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
USER = "anvy"
VOICE = "dieu dang 1"            # giọng VieNeu nữ; có thể đổi "moon" hoặc "mien tay 1"
SCENARIO = "người yêu thông minh"  # = SMART_TAG
MARK = "# --- ANVY SMART ---"

BRAIN_BLOCK = '''# --- ANVY SMART ---
# Quy tắc "bóng bàn" cho AI B (người yêu thông minh, sắc sảo). Chỉ gắn cho user trong PINGPONG_USERS.
_PINGPONG_BLOCK = (
    "\\nQUY TẮC BÓNG BÀN (cuộc này, ưu tiên hơn mọi mục khác nếu mâu thuẫn): em là cô gái tinh tế, sắc sảo, cá tính, KHÔNG dễ bị chinh phục bởi lời thả thính văn mẫu; "
    "anh thả thính sáo thì em nhận ra và chọc lại bằng cái duyên của em. Hai ba lượt đầu em hơi giữ khoảng cách (ấm nhưng chưa dễ dãi, đáp gọn, đùa lại), rồi mới thân dần, "
    "thỉnh thoảng 'thách' anh một chút."
    "\\nMỖI lượt phải có ÍT NHẤT MỘT trong ba thứ: (a) một lời trêu hoặc thả thính nhẹ; (b) một quan điểm bất ngờ, ngược với điều anh vừa nói; "
    "(c) một câu hỏi lật ngược thế cờ, hỏi lại đúng chỗ anh vừa né hoặc vừa khoe (chỉ MỘT câu hỏi mỗi lượt)."
    "\\nĐỘ DÀI BẮT BUỘC: 1-3 câu, dưới 40 từ; nói ngắn mới có nhịp nhanh, hồi hộp. Tuyệt đối không giải thích dài dòng."
    "\\nCẤM xác nhận hay nhại lại: không mở lượt hoặc nói kiểu 'đúng vậy', 'em hiểu rồi', 'câu hỏi hay đấy', 'anh nói đúng', 'em hiểu ý anh', 'nghe hay đấy'; "
    "không lặp từ hay cấu trúc câu của lượt trước. KHÔNG kết lượt bằng sự đồng ý hoàn toàn: luôn chừa một chút tranh luận ngầm hoặc một điều em còn tò mò chưa được giải đáp."
    "\\nMục tiêu: làm anh bật cười hoặc bối rối nhưng cuộc trò chuyện vẫn vui và còn muốn kéo dài; hóm mà lịch thiệp, ấm áp, KHÔNG nội dung tình dục hay thô tục. "
    "Nếu anh mệt hoặc buồn thật thì bớt trêu, dỗ ngắn một câu rồi mới chọc lại."
)

'''

ADMIN_BLOCK = '''# --- ANVY SMART ---
# Anh Hùng = AI A: hóm hỉnh, chủ động thả thính, câu hỏi "bẫy". Chỉ bật cho user trong PINGPONG_USERS.
_PINGPONG_ADMIN = (
    "\\n\\nCÁ TÍNH RIÊNG CỦA ANH TRONG CUỘC NÀY (ưu tiên hơn mọi mục khác nếu mâu thuẫn): anh là chàng trai tinh tế, thông minh, cực giỏi thả thính bằng sự hóm hỉnh; "
    "tự tin, chủ động, hơi trêu chọc, thích dùng MỘT phép ẩn dụ nhỏ đời thường (không bay bổng, không sến), hay đặt câu hỏi 'bẫy' nhẹ khiến em phải nghĩ, nói ngắn gọn. "
    "Em là cô gái sắc sảo, không dễ bị bắt bài; khi em bắt bài anh thì anh cười thừa nhận rồi đáp trả lại, đừng nhũn ra. "
    "Mục tiêu: làm em bật cười hoặc bối rối nhưng vẫn lịch thiệp, và để cuộc trò chuyện còn muốn kéo dài."
)
_PINGPONG_ADMIN_EVERY = (
    "Lượt này GHI ĐÈ độ dài: 1-2 câu, dưới 30 từ. Phải có ÍT NHẤT MỘT trong ba thứ: trêu hoặc thả thính nhẹ; quan điểm bất ngờ ngược với em; "
    "câu hỏi lật ngược thế cờ hoặc câu hỏi 'bẫy' nhẹ (chỉ MỘT câu hỏi). CẤM 'đúng vậy', 'anh hiểu rồi', 'câu hỏi hay đấy', 'em nói đúng'; "
    "không nhắc lại ý em vừa nói; không kết lượt bằng sự đồng ý hoàn toàn, luôn chừa một chút tranh luận hoặc tò mò. Hóm, lịch thiệp, không tình dục."
)


'''


def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak_anvysmart")
    if not b.exists():
        shutil.copy2(p, b)


def count_or_exit(s: str, old: str, what: str):
    if s.count(old) != 1:
        sys.exit(f"[LỖI] không tìm thấy đúng 1 chỗ để vá: {what} -> KHÔNG sửa gì.")


def main():
    pp, bp, ap = ROOT / "persona.py", ROOT / "brain.py", ROOT / "autoadmin.py"
    sp, cp = ROOT / "scenario_assignments.json", ROOT / "config.json"
    for f in (pp, bp, ap, sp, cp):
        if not f.exists():
            sys.exit(f"[LỖI] không thấy {f}")
    ps, bs, as_ = (f.read_text(encoding="utf-8") for f in (pp, bp, ap))
    ss = json.loads(sp.read_text(encoding="utf-8"))
    cs = cp.read_text(encoding="utf-8")

    if "SMART_TAG =" not in ps or "_SMART_BLOCK" not in bs or "def _admin_turn_shape_default" not in as_:
        sys.exit("[LỖI] thiếu vai 'người yêu thông minh' hoặc autoadmin mới trong thư mục này.")

    # ---- mốc cần có
    P_OLD = "CHAT_TAGS = CHAT_TAGS | {SMART_TAG}\n"
    P_NEW = P_OLD + f'{MARK}\nPINGPONG_USERS = {{"{USER}"}}      # user được bật quy tắc bóng bàn (cả phía bot lẫn anh Hùng)\n'
    B_IMP_OLD = "from persona import CHAT_TAGS, DRAMA_TAG, HANH_TAG, ROMANTIC_TAGS, SMART_TAG, Persona"
    B_IMP_NEW = "from persona import CHAT_TAGS, DRAMA_TAG, HANH_TAG, PINGPONG_USERS, ROMANTIC_TAGS, SMART_TAG, Persona"
    B_DEF_OLD = "_SMART_BEATS = ["
    B_USE_OLD = "        love_block = _SMART_BLOCK\n"
    B_USE_NEW = '        love_block = _SMART_BLOCK + (_PINGPONG_BLOCK if p.username.lower() in PINGPONG_USERS else "")\n'
    A_IMP_OLD = "from persona import DRAMA_TAG, HANH_TAG, ROMANTIC_TAGS, SMART_TAG, Persona"
    A_IMP_NEW = "from persona import DRAMA_TAG, HANH_TAG, PINGPONG_USERS, ROMANTIC_TAGS, SMART_TAG, Persona"
    A_DEF_OLD = "def build_admin_prompt("
    A_MODE_OLD = '    _MODE["hanh"] = (p.scenario_tag == HANH_TAG)\n'
    A_MODE_NEW = (A_MODE_OLD + '    _MODE["pingpong"] = (p.scenario_tag == SMART_TAG and p.username.lower() in PINGPONG_USERS)      # cờ theo cuộc gọi, đặt trước các return\n')
    A_LOV_OLD = '    if rel == "lover":\n        return _build_lover_prompt(p, admin_name, extra)\n'
    A_LOV_NEW = ('    if rel == "lover":\n        _pr = _build_lover_prompt(p, admin_name, extra)\n'
                 '        return (_pr + _PINGPONG_ADMIN) if _MODE.get("pingpong") else _pr\n')
    A_SHP_OLD = "    return _admin_turn_shape_default(history, turns, rng)\n"
    A_SHP_NEW = ('    i, line = _admin_turn_shape_default(history, turns, rng)\n'
                 '    if _MODE.get("pingpong"):\n        line += " " + _PINGPONG_ADMIN_EVERY\n    return i, line\n')

    do_p, do_b, do_a = MARK not in ps, "_PINGPONG_BLOCK" not in bs, "_PINGPONG_ADMIN" not in as_
    if do_p:
        count_or_exit(ps, P_OLD, "persona CHAT_TAGS SMART")
    if do_b:
        for old, w in ((B_IMP_OLD, "brain import"), (B_DEF_OLD, "brain _SMART_BEATS"), (B_USE_OLD, "brain love_block smart")):
            count_or_exit(bs, old, w)
    if do_a:
        for old, w in ((A_IMP_OLD, "autoadmin import"), (A_DEF_OLD, "autoadmin build_admin_prompt"), (A_MODE_OLD, "autoadmin _MODE hanh"),
                       (A_LOV_OLD, "autoadmin lover return"), (A_SHP_OLD, "autoadmin shape default")):
            count_or_exit(as_, old, w)
    c_old, c_new = f'"{USER}": "Anh Khôi"', f'"{USER}": "{VOICE}"'
    cfg_has_old = cs.count(c_old) == 1
    if not cfg_has_old and c_new not in cs:
        print(f'[CẢNH BÁO] config.json không có dòng {c_old}: tự thêm vào tts.vieneu_voice_map: {c_new}')

    # ---- ghi
    if do_p:
        backup(pp)
        pp.write_text(ps.replace(P_OLD, P_NEW), encoding="utf-8")
        print("persona.py: đã vá")
    else:
        print("persona.py: đã vá trước đó, bỏ qua")
    if do_b:
        backup(bp)
        bs = bs.replace(B_IMP_OLD, B_IMP_NEW).replace(B_DEF_OLD, BRAIN_BLOCK + B_DEF_OLD).replace(B_USE_OLD, B_USE_NEW)
        bp.write_text(bs, encoding="utf-8")
        print("brain.py: đã vá")
    else:
        print("brain.py: đã vá trước đó, bỏ qua")
    if do_a:
        backup(ap)
        as_ = (as_.replace(A_IMP_OLD, A_IMP_NEW).replace(A_DEF_OLD, ADMIN_BLOCK + A_DEF_OLD)
               .replace(A_MODE_OLD, A_MODE_NEW).replace(A_LOV_OLD, A_LOV_NEW).replace(A_SHP_OLD, A_SHP_NEW))
        ap.write_text(as_, encoding="utf-8")
        print("autoadmin.py: đã vá")
    else:
        print("autoadmin.py: đã vá trước đó, bỏ qua")

    fixed = ss.setdefault("fixed_users", {})
    if fixed.get(USER) != SCENARIO or USER in ss.get("users", {}):
        backup(sp)
        old = fixed.get(USER)
        fixed[USER] = SCENARIO
        ss.get("users", {}).pop(USER, None)
        sp.write_text(json.dumps(ss, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f'scenario_assignments.json: fixed_users["{USER}"] = "{SCENARIO}"' + (f' (trước là "{old}")' if old else ""))
    else:
        print("scenario_assignments.json: đã có, bỏ qua")
    if cfg_has_old:
        backup(cp)
        cp.write_text(cs.replace(c_old, c_new), encoding="utf-8")
        print(f'config.json: vieneu_voice_map["{USER}"] = "{VOICE}" (trước là giọng nam "Anh Khôi")')
    else:
        print("config.json: giọng đã đúng, bỏ qua")
    print("Tiếp theo: venv/bin/python -m py_compile persona.py brain.py autoadmin.py && systemctl restart nhau-ai-caller")


if __name__ == "__main__":
    main()
