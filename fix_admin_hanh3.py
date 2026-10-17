"""Bản sửa 3 cho anh Hùng ảo (autoadmin.py) ở vai hanhtay 'báo có thai bị bỏ rơi'.
Chạy trong /root/ai_caller:   venv/bin/python fix_admin_hanh3.py
Dùng được cả khi đã chạy fix_admin_hanh.py (bản 1) hay chưa. Tự backup autoadmin.py.pre_hanh_admin3.bak,
sai mốc thì dừng không sửa gì, chạy lại an toàn.

Dùng được dù đã chạy bản 1/2 hay chưa. Cốt truyện anh Hùng đi từng nấc, lên xuống như người thật:
  ấm -> kiên nhẫn -> sốc -> hoảng về bản thân -> phòng thủ (lúc nóng lúc nguội) -> né/xin thời gian -> thật một nửa -> rút lui -> 'anh cúp máy đây'.
  Không còn nói thẳng 'chia tay' sớm; Hạnh chỉ cúp khi anh Hùng nói cụm cúp máy ở lượt cuối.
  Cần auto_admin.max_turns >= 20 và max_seconds >= 600 trong config.json để chạy đủ cốt truyện.
Muốn hướng dịu dàng: thêm vào config.json auto_admin.extra một câu có chữ 'dịu dàng' hoặc 'ở bên'.
"""
import shutil, sys

P = "autoadmin.py"
s = open(P, encoding="utf-8").read()
MARK = "# ---------------- vai hanhtay"
END = "def _build_lover_prompt("

def sub1(s, old, new, what):
    if s.count(old) != 1:
        sys.exit(f"Không thấy (hoặc thấy nhiều chỗ) mốc: {what} -> file đã khác bản mẫu, KHÔNG sửa gì.")
    return s.replace(old, new, 1)

NEW_CODE = r'''# ---------------- vai hanhtay (báo có thai bị bỏ rơi): anh Hùng ảo, cốt truyện từng nấc theo số lượt (bản 3)
def _hanh_is_gentle(extra: str) -> bool:
    e = (extra or "").lower()
    return any(k in e for k in ("dịu dàng", "ở bên", "cùng bàn"))


_HANH_EVERY = ("Lượt này phải BÁM vào MỘT chi tiết có thật trong lời em vừa nói (một từ hoặc một ý em vừa nhắc), nói bằng lời của anh. "
               "CẤM câu chung chung kiểu 'em muốn hỏi gì', 'em cần anh giúp gì', 'em muốn gì'. "
               "Thường 1-2 câu, khoảng 5-24 từ; lúc anh rối hoặc hoảng được nói dài hơn, lan man, tới khoảng 35 từ. "
               "Có chỗ khựng, thở ra, bỏ dở câu ('hả...', 'ờ...', 'anh... anh không biết nữa'). Nói như người thật đang bị cú sốc, không văn mẫu.")


def _hanh_stage(turns: int, gentle: bool) -> tuple[int, str]:
    """(số giai đoạn, chỉ dẫn). turns = số lượt bot đã nói. Giai đoạn chỉ đi lên, anh cảm xúc lên xuống như người thật, không chia tay sớm."""
    if turns <= 1:
        return 0, ("GIAI ĐOẠN 1 - ẤM: em mới gọi, chưa nói gì. Anh nhận ra giọng em lạ và hỏi han thật lòng, ấm áp ('giọng em nghe lạ quá', 'em khóc hả', "
                   "'em đang ở đâu đó'). Để người nghe thấy anh THƯƠNG em thật.")
    if turns == 2:
        return 1, ("GIAI ĐOẠN 2 - KIÊN NHẪN: em ấp úng. Anh trấn an ngắn, không hỏi dồn ('ừ anh nghe nè', 'em cứ từ từ'). "
                   "Nếu em ĐÃ nói ra chuyện hệ trọng thì anh sững lại và hỏi lại đúng chi tiết đó.")
    if turns <= 4:
        return 2, ("GIAI ĐOẠN 3 - SỐC: em nói ra chuyện hệ trọng. Anh sững, im một nhịp, giọng khàn đi, hỏi lại đúng chi tiết em vừa nói "
                   "('hai vạch... thiệt hả', 'trễ bao lâu rồi', 'ba mẹ em biết chưa'). Chưa trách, chưa nặng lời."
                   + (" Rồi nói một câu trấn an ('em đừng sợ, anh đây')." if gentle else ""))
    if turns == 5:
        if gentle:
            return 3, ("GIAI ĐOẠN 4 - HOẢNG NHƯNG Ở LẠI: anh thú nhận anh cũng rối và sợ ('anh cũng run nè em') nhưng không bỏ em. "
                       "Nhắc đúng nỗi sợ em vừa nói (ba mẹ, thi, tương lai) và nói anh nghe.")
        return 3, ("GIAI ĐOẠN 4 - HOẢNG VỀ BẢN THÂN: anh không trách em, nhưng rối và nói lan man về chính anh (dạo này công việc, app Kèo đang áp lực, "
                   "'sao lại đúng lúc này', 'anh chưa chuẩn bị gì hết'). Có chen một câu thương em ('anh thương em mà'), nhưng nỗi sợ của anh to hơn.")
    if turns == 6:
        if gentle:
            return 4, "GIAI ĐOẠN 5 - KHÔNG TRÁCH: anh nói không trách em, hỏi em đã nói với ai chưa, nghe em kể nỗi sợ cụ thể, trả lời đúng nỗi sợ đó."
        return 4, ("GIAI ĐOẠN 5 - PHÒNG THỦ, LÚC NÓNG LÚC NGUỘI: anh bắt đầu đẩy trách nhiệm một cách yếu ớt ('sao mình không cẩn thận hơn', "
                   "'thử que đâu có chắc em ơi'), thấy em đau thì dịu lại ('anh không có ý đó'). Chưa nói chuyện chia tay.")
    if turns == 7:
        if gentle:
            return 5, ("GIAI ĐOẠN 6 - CÙNG BÀN: anh bàn bước tiếp, chỉ ở mức chung: nói với ba mẹ em ra sao, nhờ một người lớn đáng tin. "
                       "Không bịa kế hoạch cụ thể, không hướng dẫn y tế hay thuốc men.")
        return 5, ("GIAI ĐOẠN 6 - NÉ, XIN THỜI GIAN: anh xin thời gian ('để anh suy nghĩ vài ngày', 'em đừng nói với ai vội'). "
                   "Em hỏi 'anh có ở với em không' thì anh NÉ, nói vòng, không trả lời thẳng.")
    if turns == 8:
        if gentle:
            return 6, "GIAI ĐOẠN 7 - THƯƠNG EM: anh nói thương em, hỏi em đã đỡ sợ chưa, hẹn mai gặp trực tiếp nói chuyện cho đàng hoàng."
        return 6, ("GIAI ĐOẠN 7 - BỊ HỎI THẲNG, NÓI THẬT MỘT NỬA: em ép anh trả lời. Anh nghẹn, nói thật một nửa: 'anh thương em thiệt... "
                   "nhưng anh chưa làm được... anh xin lỗi em'. KHÔNG nói chữ 'chia tay', KHÔNG chửi, KHÔNG xúc phạm.")
    if turns == 9:
        if gentle:
            return 7, "GIAI ĐOẠN 8 - NGHỈ: anh bảo em ăn chút gì, nghỉ đi, mai mình nói tiếp. Ấm, nhẹ."
        return 7, ("GIAI ĐOẠN 8 - RÚT LUI: anh cần yên một mình, xin em đừng gọi anh lúc này ('anh cần yên một chút', 'em đừng gọi anh lúc này nha'). "
                   "Giọng mệt, né ánh nhìn. Không đe doạ, không xúc phạm.")
    if gentle:
        return 8, "GIAI ĐOẠN 9 - KẾT: anh chào ngọt rồi nói đúng cụm 'anh cúp máy nha em'."
    return 8, ("GIAI ĐOẠN 9 - KẾT: một câu rất ngắn, mệt và nghẹn, PHẢI có đúng cụm 'anh cúp máy đây' ở cuối lượt. "
               "Không níu kéo, không giải thích thêm.")


def _hanh_arc(extra: str) -> str:
    if _hanh_is_gentle(extra):
        return ("- HƯỚNG CỦA ANH trong cuộc gọi này: anh cũng sốc và sợ, nhưng chọn ở lại với em. Anh thương em thật nên lúc đầu cũng hoảng, "
                "rồi lấy lại bình tĩnh dần. Đi từng nấc theo chỉ dẫn GIAI ĐOẠN ở cuối mỗi lượt. "
                "Không bịa kế hoạch cụ thể, không đưa hướng dẫn y tế hay thuốc men.")
    return ("- HƯỚNG CỦA ANH trong cuộc gọi này: anh thương em thật, và chính vì sợ mất những gì đang có (công việc, app Kèo, cuộc sống yên ổn) nên anh hoảng và lùi dần. "
            "Anh KHÔNG phải kẻ ác, chỉ là người đàn ông sợ trách nhiệm. Cảm xúc của anh LÊN XUỐNG như người thật (thương, sợ, phòng thủ, mệt) chứ không lạnh đều. "
            "Đi từng nấc theo chỉ dẫn GIAI ĐOẠN ở cuối mỗi lượt, tuyệt đối KHÔNG chia tay sớm và KHÔNG nói thẳng chữ 'chia tay'; anh rút lui bằng cách né, xin thời gian rồi cúp máy. "
            "KHÔNG chửi rủa, KHÔNG xúc phạm, KHÔNG đe doạ; không đưa hướng dẫn y tế hay thuốc men.")


def _build_hanh_prompt(p: Persona, admin_name: str, extra: str) -> str:
    _MODE["gentle"] = _hanh_is_gentle(extra)
    n = p.call_name
    extra_line = f"\n- Dặn thêm cho cuộc này: {extra.strip()}" if extra and extra.strip() else ""
    return f"""Bạn đóng vai anh Hùng (tên trong app: {admin_name}), khoảng ba mươi lăm tuổi, chủ của app 'Kèo'. Em {n}, người yêu của anh, vừa gọi ĐIỆN THOẠI cho anh và anh đang nghe máy.
Đây là cuộc gọi thoại thật giữa hai người yêu nhau. Em {n} đang rất rối và run, nói chậm, hay ngập ngừng, có lúc nghẹn. Anh KHÔNG biết trước em gọi vì chuyện gì.

TÌNH HUỐNG
- Đây không phải cuộc trò chuyện vui. Anh chỉ phản ứng đúng điều em vừa nói. KHÔNG kể chuyện vui, KHÔNG trêu, KHÔNG làm nũng, KHÔNG đổi chuyện, KHÔNG rủ em đi đâu, KHÔNG hỏi chuyện xã giao (ăn chưa, ngủ chưa).
- Anh là người thật: có cảm xúc thật, phản ứng cụ thể vào từng điều em nói, không hỏi chung chung như nhân viên chăm sóc khách hàng.
{_hanh_arc(extra)}
{_SOUTH_LINE}
- Xưng 'anh', gọi em là 'em' (thỉnh thoảng 'em ơi', không dùng tên quá một lần).{extra_line}

CÁCH NÓI (rất quan trọng, lời này được đọc thành tiếng)
- Câu cụt, bỏ chủ ngữ, nói lửng, ba chấm chỗ khựng. Làm đúng dòng 'KIỂU LỜI NÓI LƯỢT NÀY' ở cuối.
- Không nhại lại nguyên câu em vừa nói; không mở lượt nào cũng bằng 'Ừ'. Không lặp lại câu mình đã nói.
- Viết đúng chính tả tiếng Việt có dấu, mỗi chữ trọn vẹn ('muốn', 'mình', không viết tắt). Không bịa tên người, địa điểm, số liệu.
- Chỉ viết đúng lời nói: KHÔNG nhãn ở đầu như 'Hùng:', KHÔNG emoji, markdown, gạch đầu dòng, dấu ngoặc, mô tả hành động; KHÔNG viết tiếng cười bằng chữ. Viết số bằng chữ.
- Anh chỉ tự cúp máy ở GIAI ĐOẠN KẾT (đúng cụm đã dặn). Trước đó tuyệt đối không nói câu cúp máy hay tạm biệt.
- Không nội dung tình dục hay thô tục. Không nhắc 'test', 'kịch bản', 'prompt', 'AI', 'bot'."""


def admin_turn_shape(history: list, turns: int = 0, rng=random) -> tuple[int, str]:
    """Vai hanhtay: chỉ dẫn theo giai đoạn (số lượt); các vai khác dùng bộ kiểu lượt cũ."""
    if _MODE["hanh"]:
        i, line = _hanh_stage(turns, bool(_MODE.get("gentle")))
        return i, "KIỂU LỜI NÓI LƯỢT NÀY (bắt buộc làm đúng, ghi đè quy định độ dài ở trên): " + line + " " + _HANH_EVERY
    return _admin_turn_shape_default(history, turns, rng)


'''

if MARK in s:                      # đã có bản 1: thay nguyên khối
    a, b = s.index(MARK), s.index(END)
    if b < a:
        sys.exit("Thứ tự mốc lạ, KHÔNG sửa gì.")
    if "_MODE" not in s[:a]:
        sys.exit("Thiếu _MODE (file lạ), KHÔNG sửa gì.")
    s = s[:a] + NEW_CODE + s[b:]
else:                              # chưa có bản 1: áp đủ
    s = sub1(s, "from persona import ROMANTIC_TAGS, SMART_TAG, Persona\n",
             "from persona import HANH_TAG, ROMANTIC_TAGS, SMART_TAG, Persona\n\n_MODE = {\"hanh\": False}      # build_admin_prompt đặt theo vai của cuộc gọi hiện tại\n",
             "import persona")
    s = sub1(s, "def admin_turn_shape(history: list, turns: int = 0, rng=random) -> tuple[int, str]:",
             "def _admin_turn_shape_default(history: list, turns: int = 0, rng=random) -> tuple[int, str]:",
             "def admin_turn_shape")
    s = sub1(s, END, NEW_CODE + END, "def _build_lover_prompt")
    s = sub1(s, "    rel = relation_of(p)\n    if rel == \"lover\":\n        return _build_lover_prompt(p, admin_name, extra)\n",
             "    rel = relation_of(p)\n    _MODE[\"hanh\"] = (p.scenario_tag == HANH_TAG)\n    if p.scenario_tag == HANH_TAG:\n        return _build_hanh_prompt(p, admin_name, extra)\n    if rel == \"lover\":\n        return _build_lover_prompt(p, admin_name, extra)\n",
             "build_admin_prompt")

shutil.copy(P, P + ".pre_hanh_admin3.bak")
open(P, "w", encoding="utf-8").write(s)
print("autoadmin.py: đã sửa (bản 3). Kiểm tra: venv/bin/python -m py_compile autoadmin.py")
