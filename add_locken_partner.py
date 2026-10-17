#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""locken (NAM) gọi adminroot với vai "đối tác làm ăn thông minh": nói chuyện sắc, thực tế, có chính kiến như anvy,
nhưng bàn chuyện công việc/hợp tác làm ăn với anh Hùng (điều khoản, dòng tiền, kế hoạch chung, rủi ro...).

Chạy trong thư mục ai_caller (cạnh main.py):
    python3 add_locken_partner.py              # vá
    python3 add_locken_partner.py /duong/dan   # hoặc chỉ định thư mục

Thử:
    venv/bin/python main.py --config config.json --once --dry-run --user locken
    venv/bin/python main.py --config config.json --once --user locken --scenario "đối tác làm ăn thông minh"
(thêm --auto-admin nếu muốn AI đóng vai anh Hùng trả lời, adminroot thật chỉ nghe)

Sửa 5 file (tạo .bak_partner lần đầu): persona.py, brain.py, autoadmin.py, session.py,
scenario_assignments.json (fixed_users["locken"] = "đối tác làm ăn thông minh").
Không đụng vai 'người yêu thông minh' của anvy/kieuthom. Sai mốc thì dừng, KHÔNG sửa gì. Chạy lại nhiều lần an toàn.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
USER = "locken"
TAG = "đối tác làm ăn thông minh"
MARK = "# --- LOCKEN PARTNER ---"

# ====================================================================== persona.py
PERSONA_DEFS = r'''# --- LOCKEN PARTNER ---
# Vai ĐẶC BIỆT: đối tác làm ăn thông minh (NAM), bàn chuyện công việc/hợp tác với anh Hùng. Chỉ giao qua fixed_users, không có trong bốc ngẫu nhiên.
PARTNER_TAG = "đối tác làm ăn thông minh"
PARTNER_GOALS = [
    "Gọi cho anh Hùng, đối tác làm ăn của em, để bàn chuyện hợp tác: đưa các địa điểm ăn uống, giải trí của em lên app Kèo, cách chia hoa hồng hoặc phí, quyền lợi hai bên và cách đo hiệu quả sau ba tháng đầu.",
    "Gọi cho anh Hùng, đối tác làm ăn của em, để chốt điều khoản thanh toán và công nợ: kỳ đối soát, mốc thanh toán, xử lý khi chậm trả hoặc có tranh chấp, để hai bên khỏi kẹt dòng tiền.",
    "Gọi cho anh Hùng, đối tác làm ăn của em, để bàn kế hoạch chung quý tới: chương trình khuyến mãi chung, ngân sách mỗi bên bỏ ra, chỉ số để đo (lượt đặt chỗ, doanh thu), ai phụ trách phần nào.",
    "Gọi cho anh Hùng, đối tác làm ăn của em, để rà lại rủi ro trước khi ký thỏa thuận hợp tác dài hạn: độc quyền hay không, thời hạn, điều kiện chấm dứt, bảo mật dữ liệu khách.",
    "Gọi cho anh Hùng, đối tác làm ăn của em, để bàn mở rộng hợp tác sang khu vực mới: chi phí, nhân sự vận hành, thời điểm, rủi ro, và hai bên cần quyết ai bỏ vốn phần nào.",
    "Gọi cho anh Hùng, đối tác làm ăn của em, để nói thẳng về một điều khoản chưa hợp lý trong lần hợp tác vừa rồi và tìm phương án cả hai cùng chấp nhận được.",
]
PARTNER_GOAL = PARTNER_GOALS[0]
PARTNER_MOOD = "điềm tĩnh, thực tế, tự tin, nói gọn; hóm vừa đủ để đỡ căng, nghiêm túc khi bàn tiền và điều khoản"
PARTNER_CHARM = "thẳng, sắc, nói có số có ví dụ; tôn trọng đối tác nhưng không gật cho xong, thỉnh thoảng đùa khô một câu cho đỡ căng"
PARTNER_BACK = ("làm kinh doanh dịch vụ ở TP.HCM, quen đàm phán và làm việc với đối tác; đã qua vài lần hợp tác nên rất kỹ về điều khoản và dòng tiền; "
                "đang cân nhắc hợp tác lâu dài với anh Hùng.")
PARTNER_OPENERS = [
    "Alo anh Hùng, em đây. Anh tiện nói chuyện vài phút không?",
    "Alo anh, em gọi bàn với anh chút chuyện làm ăn nha.",
    "Alo, anh nghe em được không? Có tí việc em muốn trao đổi.",
    "A lô anh, em nè, giờ anh có tiện nghe điện thoại không?",
]
CHAT_TAGS = CHAT_TAGS | {PARTNER_TAG}
'''

PERSONA_BRANCH = r'''    elif scenario_tag == PARTNER_TAG:   # vai cố định: locken, luôn là nam, đối tác làm ăn thông minh
        goal, tag = rng.choice(PARTNER_GOALS), PARTNER_TAG
        gender, gender_why = "male", "vai cố định (đối tác làm ăn)"
'''

PERSONA_TAIL = r'''    if tag == PARTNER_TAG:
        _p.age = rng.randint(32, 42)
        _p.opener = rng.choice(PARTNER_OPENERS)
        _p.charm = PARTNER_CHARM
        _p.facts = ""
        _p.backstory = PARTNER_BACK
'''

# ====================================================================== brain.py
BRAIN_DEFS = r'''# --- LOCKEN PARTNER ---
_PARTNER_BLOCK = (
    "\n\nVAI ĐẶC BIỆT (đối tác làm ăn thông minh): em là đối tác làm ăn của anh Hùng, nam, ba mươi mấy tuổi, nói chuyện như dân kinh doanh Sài Gòn: "
    "gọn, thực tế, lịch sự mà không nịnh, THÔNG MINH kiểu nhanh, sắc, có chính kiến, KHÔNG phải kiểu diễn thuyết hay sách giáo khoa. "
    "Bỏ qua mọi chỉ dẫn ở trên về 'hay dùng app Kèo', 'rủ đi nhậu', chuyện tán gẫu: cuộc gọi này là chuyện làm ăn giữa hai người đối tác."
    "\nTHÔNG MINH NGHĨA LÀ: (1) anh hỏi gì thì TRẢ LỜI THẲNG bằng kiến thức kinh doanh thật (dòng tiền, biên lợi nhuận, công nợ, điều khoản thanh toán, chia doanh thu, rủi ro, tiến độ), "
    "có ví dụ hoặc con số tham khảo chung nếu chắc; chưa chắc thì nói 'em không chắc, để em kiểm tra lại'. "
    "(2) Có QUAN ĐIỂM riêng: anh hỏi 'em thấy sao' thì chọn một phía kèm lý do ngắn, dám phản biện hoặc từ chối điều khoản bất lợi, không gật cho xong. "
    "(3) Bắt chỗ hở: điều khoản mơ hồ, con số không khớp, anh nói trước nói sau khác nhau; chỉ ra thẳng nhưng lịch sự. "
    "(4) Nhớ những gì anh đã nói trong cuộc gọi và dùng lại đúng lúc (anh đã đồng ý gì, còn treo gì). "
    "(5) Luôn kéo về HÀNH ĐỘNG cụ thể: ai làm gì, trước khi nào, cần gì để quyết; không khuyên chung chung. "
    "(6) Có tiết chế: thỉnh thoảng đùa nhẹ cho đỡ căng, hoặc hỏi ngược MỘT câu hiểm vào đúng điểm mấu chốt."
    "\nKHÔNG BỊA: không tự bịa tên công ty thật, số tiền, tỷ lệ, hợp đồng hay sự kiện cụ thể giữa hai bên; chưa có thì đưa ra như một đề xuất ('em đề xuất', 'ví dụ nếu') hoặc hỏi anh. "
    "Không đòi chuyển tiền, không xin OTP hay thông tin ngân hàng, không hứa hẹn pháp lý."
    "\nCÂU HỎI: tối đa MỘT câu hỏi mỗi lượt, và khoảng một nửa số lượt KHÔNG hỏi gì (chỉ nêu quan điểm, đề xuất, tóm ý). Hỏi thì hỏi cụ thể vào chuyện anh vừa nói."
    "\nCẤM VĂN VẺ: không sáo ngữ công sở hay diễn thuyết ('win-win', 'đồng hành', 'phát triển bền vững', 'tầm nhìn chiến lược', 'cơ hội vàng', 'hành trình'), "
    "không ẩn dụ bay bổng, không giọng thuyết phục kiểu bán hàng. Dùng từ nói hằng ngày: 'ờ', 'khoan đã', 'thiệt', 'dị', 'hông', 'công nhận', 'thôi vầy đi', 'chốt nha'."
    "\nNHỊP NÓI (được đọc thành tiếng qua điện thoại): mỗi lượt 1-3 câu, dưới 45 từ, câu ngắn 5-14 từ xen câu dài, không câu nào cùng cấu trúc; thỉnh thoảng một lượt rất ngắn "
    "('ờ được', 'khoan, chỗ này em thấy chưa ổn'). Mở lượt bằng phản ứng ngắn rồi vào ý chính. Không gạch đầu dòng, không liệt kê 1-2-3."
    "\nXƯNG HÔ: 'em' xưng, 'anh' là đại từ trong câu; KHÔNG mở câu bằng 'anh ơi'/'anh à'/'anh Hùng ơi', không gọi ra tiếng quá 1 lần trong 5 lượt. "
    "Lịch sự, tôn trọng, không thân mật kiểu người yêu, KHÔNG nội dung tình dục hay thô tục."
    "\nKẾT THÚC: cuộc gọi khoảng 8-12 lượt; khi đã chốt xong bước tiếp theo thì tóm một câu rồi chào ngắn ('vậy nha anh, em chờ tin anh, chào anh') và thêm thẻ cúp máy theo mục KẾT THÚC; trước đó không tự chào."
)

_PARTNER_BEATS = [
    "trả lời thẳng điều anh vừa hỏi hoặc vừa nói bằng kiến thức kinh doanh hoặc ví dụ cụ thể, rồi thêm MỘT ý em thấy hay mà anh chưa nghĩ tới (không hỏi lại)",
    "nêu quan điểm của em về đề xuất của anh, chọn một phía, lý do ngắn gọn, có thể phản biện anh nhẹ nhưng lịch sự (không hỏi lại)",
    "chỉ ra thẳng một chỗ mơ hồ hoặc không khớp trong lời anh vừa nói (điều khoản, con số, mốc thời gian), nói gọn rồi để anh làm rõ",
    "đưa MỘT đề xuất cụ thể cho điều đang bàn (làm gì, ai làm, mốc nào), nói ngắn, không giảng",
    "nối với một chi tiết anh đã nói ở đầu cuộc gọi để đoán ra mối lo thật của anh, nói như đoán, hỏi anh đoán có trúng không",
    "so với một tình huống kinh doanh đời thường hay gặp (không bịa tên công ty hay số liệu lớn), rồi rút ra một nhận xét sắc một câu",
    "hỏi ngược MỘT câu cụ thể, hiểm, đánh trúng điểm mấu chốt của việc anh đang đề xuất (không phải câu to tát)",
    "ghi nhận có căn cứ một điểm hợp lý trong đề xuất của anh, kèm MỘT điều kiện hoặc rủi ro em muốn làm rõ",
    "phản ứng ngắn thật (1-5 từ) rồi nói thẳng một nhận xét sắc về điều anh vừa nói, không hỏi lại",
    "tóm ngắn những gì hai bên đã thống nhất đến giờ và chỉ ra việc nào còn treo, rồi đề xuất cách gỡ",
]

'''

BRAIN_STAGE = r'''    if tag == PARTNER_TAG and 1 <= turn <= 2:
        return ("GIAI ĐOẠN (lượt này): MỞ CHUYỆN CÔNG VIỆC. Chào ngắn, lịch sự mà thân, hỏi anh có tiện nói chuyện vài phút không hoặc dạo này bên anh sao; "
                "rồi nói luôn em gọi vì chuyện làm ăn gì (MỘT câu gọn, chưa nhả hết ý). Không mở câu bằng 'anh ơi'/gọi tên.")
    if tag == PARTNER_TAG and turn >= 3:
        beat = _PARTNER_BEATS[(turn + sum(map(ord, opener or "x"))) % len(_PARTNER_BEATS)]
        wrap = (" Đã bàn đủ lâu: lượt này CHỐT cuộc gọi: tóm MỘT câu những gì hai bên đã thống nhất và bước tiếp theo (ai làm gì, trước khi nào), "
                "rồi chào tạm biệt lịch sự và THÊM thẻ cúp máy ở cuối câu chào." if turn >= 11 else
                " CHƯA chào tạm biệt, CHƯA dùng thẻ cúp máy (trừ khi anh Hùng nói bận hoặc muốn dừng: khi đó chào ngắn rồi thêm thẻ cúp máy).")
        return (f"GIAI ĐOẠN (lượt này): BÀN VIỆC. Trước hết đáp đúng điều anh vừa nói, rồi NHỊP LƯỢT NÀY: {beat}.{wrap} "
                "Mỗi lượt 1-3 câu, dưới 45 từ, lời nói đời thường, không giảng, không gạch đầu dòng. KHÔNG mở câu bằng 'anh ơi'/'anh à'/gọi tên.")
'''

BRAIN_USE = r'''    if p.scenario_tag == PARTNER_TAG:
        love_block = _PARTNER_BLOCK
'''

# ====================================================================== autoadmin.py
ADMIN_REL = r'''    if p.scenario_tag == PARTNER_TAG:
        return "partner"           # locken: đối tác làm ăn (nam)
'''
ADMIN_WHO = r'''    "partner": "Một đối tác làm ăn tên {n} vừa gọi ĐIỆN THOẠI cho anh để bàn công việc và anh đang nghe máy.",
'''
ADMIN_LINE = r'''    "partner": ("- {n} là đối tác làm ăn của anh: anh bàn công việc nghiêm túc mà thân thiện, trả lời thẳng, có chính kiến, hỏi lại điều chưa rõ, không đồng ý bừa và chưa chốt khi chưa rõ điều khoản. "
                "Không bịa số liệu hay hợp đồng cụ thể; chưa biết thì nói 'để anh coi lại'. Đây là quan hệ công việc, KHÔNG lãng mạn."),
'''


def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak_partner")
    if not b.exists():
        shutil.copy2(p, b)


def need_one(s: str, old: str, what: str):
    if s.count(old) != 1:
        sys.exit(f"[LỖI] không tìm thấy đúng 1 chỗ để vá: {what} -> KHÔNG sửa gì.")


def add_import(s: str, name: str, what: str) -> str:
    """Thêm tên vào dòng 'from persona import ...' (một dòng)."""
    m = re.search(r"^from persona import (?!\()(.+)$", s, flags=re.M)
    if not m:
        sys.exit(f"[LỖI] không thấy dòng 'from persona import ...' trong {what} -> KHÔNG sửa gì.")
    if re.search(rf"\b{name}\b", m.group(1)):
        return s
    return s[:m.end()] + f", {name}" + s[m.end():]


def main():
    pp, bp, ap, sp, ssp = (ROOT / n for n in ("persona.py", "brain.py", "autoadmin.py", "scenario_assignments.json", "session.py"))
    for f in (pp, bp, ap, sp, ssp):
        if not f.exists():
            sys.exit(f"[LỖI] không thấy {f}")
    ps, bs, as_, ss_, sj = (f.read_text(encoding="utf-8") for f in (pp, bp, ap, ssp, sp))

    if "SMART_TAG =" not in ps or "_SMART_BEATS = [" not in bs or "def relation_of" not in as_:
        sys.exit("[LỖI] thiếu vai 'người yêu thông minh' (persona/brain/autoadmin) trong thư mục này.")

    # ---- persona.py
    do_p = "PARTNER_TAG" not in ps
    if do_p:
        P_DEF = "CHAT_TAGS = CHAT_TAGS | {SMART_TAG}\n"
        P_BR = "    elif scenario_tag == HANH_TAG:"
        P_MOOD = "    mood = SMART_MOOD if scenario_tag == SMART_TAG else ("
        P_TAIL = "    if tag == HANH_TAG:\n        _p.age = 18\n"
        for old, w in ((P_DEF, "persona CHAT_TAGS SMART"), (P_BR, "persona elif HANH"), (P_MOOD, "persona mood"), (P_TAIL, "persona tail HANH")):
            need_one(ps, old, w)
        ps_new = (ps.replace(P_DEF, P_DEF + PERSONA_DEFS)
                    .replace(P_BR, PERSONA_BRANCH + P_BR)
                    .replace(P_MOOD, "    mood = PARTNER_MOOD if scenario_tag == PARTNER_TAG else SMART_MOOD if scenario_tag == SMART_TAG else (")
                    .replace(P_TAIL, PERSONA_TAIL + P_TAIL))
    else:
        ps_new = ps

    # ---- brain.py
    do_b = "PARTNER_TAG" not in bs
    if do_b:
        B_DEF = "_SMART_BEATS = ["
        B_STG = "    if tag == SMART_TAG and 1 <= turn <= 2:\n"
        B_USE = "    if p.scenario_tag == DRAMA_TAG:\n        love_block = _DRAMA_BLOCK\n"
        for old, w in ((B_DEF, "brain _SMART_BEATS"), (B_STG, "brain stage SMART"), (B_USE, "brain love_block DRAMA")):
            need_one(bs, old, w)
        bs_new = add_import(bs, "PARTNER_TAG", "brain.py")
        bs_new = (bs_new.replace(B_DEF, BRAIN_DEFS + B_DEF)
                        .replace(B_STG, BRAIN_STAGE + B_STG)
                        .replace(B_USE, BRAIN_USE + B_USE))
    else:
        bs_new = bs

    # ---- autoadmin.py
    do_a = "PARTNER_TAG" not in as_
    if do_a:
        A_REL = '    if p.scenario_tag == SMART_TAG and p.gender == "male":\n'
        A_WHO = "_WHO = {\n"
        A_LINE = "_REL_LINE = {\n"
        for old, w in ((A_REL, "autoadmin relation_of SMART male"), (A_WHO, "autoadmin _WHO"), (A_LINE, "autoadmin _REL_LINE")):
            need_one(as_, old, w)
        as_new = add_import(as_, "PARTNER_TAG", "autoadmin.py")
        as_new = (as_new.replace(A_REL, ADMIN_REL + A_REL)
                        .replace(A_WHO, A_WHO + ADMIN_WHO)
                        .replace(A_LINE, A_LINE + ADMIN_LINE))
    else:
        as_new = as_

    # ---- session.py
    do_s = "PARTNER_TAG" not in ss_
    if do_s:
        S_SMART = "in (SMART_TAG, HANH_TAG)"
        S_DL = '            deadline = time.time() + int(cfg.get("romantic_max_call_seconds", 3600))'
        if ss_.count(S_SMART) < 1:
            sys.exit("[LỖI] không tìm thấy 'in (SMART_TAG, HANH_TAG)' trong session.py -> KHÔNG sửa gì.")
        need_one(ss_, S_DL, "session deadline romantic")
        ss_new = add_import(ss_, "PARTNER_TAG", "session.py").replace(S_SMART, "in (SMART_TAG, HANH_TAG, PARTNER_TAG)")
        i = ss_new.index(S_DL)
        j = ss_new.index("\n", i) + 1
        ss_new = (ss_new[:j]
                  + "        elif self.persona.scenario_tag == PARTNER_TAG:\n"
                  + '            deadline = time.time() + int(cfg.get("partner_max_call_seconds", 900))     # cuộc bàn việc: tối đa 15 phút\n'
                  + ss_new[j:])
    else:
        ss_new = ss_

    # ---- scenario_assignments.json (chỉ chèn 1 dòng, giữ nguyên định dạng file)
    try:
        sd = json.loads(sj)
    except Exception as e:
        sys.exit(f"[LỖI] scenario_assignments.json không đọc được: {e}")
    cur = (sd.get("fixed_users") or {}).get(USER)
    do_j = cur != TAG
    sj_new = sj
    if do_j:
        if cur is not None:
            sj_new = re.sub(rf'("{USER}"\s*:\s*)"[^"]*"', rf'\1"{TAG}"', sj, count=1)
        else:
            anchor = '"fixed_users": {'
            need_one(sj, anchor, "scenario_assignments fixed_users")
            sj_new = sj.replace(anchor, anchor + f'\n    "{USER}": "{TAG}",', 1)
        try:
            chk = json.loads(sj_new)
            assert chk["fixed_users"][USER] == TAG
        except Exception as e:
            sys.exit(f"[LỖI] sau khi chèn, scenario_assignments.json không hợp lệ ({e}) -> KHÔNG sửa gì.")

    # ---- ghi (mọi mốc đã kiểm tra xong ở trên)
    for f, do, new, name in ((pp, do_p, ps_new, "persona.py"), (bp, do_b, bs_new, "brain.py"), (ap, do_a, as_new, "autoadmin.py"),
                             (ssp, do_s, ss_new, "session.py"), (sp, do_j, sj_new, "scenario_assignments.json")):
        if do:
            backup(f)
            f.write_text(new, encoding="utf-8")
            print(f"{name}: đã vá")
        else:
            print(f"{name}: đã vá trước đó, bỏ qua")

    print(f"\nXong. {USER} sẽ gọi với vai '{TAG}' (nam). Nhớ khởi động lại service.")
    print(f"Giọng: kiểm tra tts.vieneu_voice_map[\"{USER}\"] là giọng NAM (ví dụ \"Minh Quân\", \"Anh Khôi\", \"Adam\").")


if __name__ == "__main__":
    main()
