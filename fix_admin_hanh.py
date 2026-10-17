"""Sửa anh Hùng ảo (autoadmin.py) cho vai hanhtay 'báo có thai bị bỏ rơi'.
Chạy trong /root/ai_caller:   venv/bin/python fix_admin_hanh.py
Tự backup autoadmin.py.pre_hanh_admin.bak, chạy lại an toàn (đã sửa thì bỏ qua), sai mốc thì dừng, không sửa nửa chừng.

Sau khi sửa, khi người gọi là Hạnh (HANH_TAG) thì anh Hùng ảo:
  - biết em đang rối/run, chưa biết em gọi vì chuyện gì, chỉ nghe + phản ứng ngắn;
  - KHÔNG kể chuyện, KHÔNG trêu, KHÔNG rủ, KHÔNG đổi chuyện (các kiểu lượt cũ của vai người yêu thông minh bị tắt);
  - mặc định đi hướng 'bị bỏ rơi' (sững -> nghi ngờ -> không nhận -> chia tay);
    muốn thử hướng dịu dàng: thêm vào config.json auto_admin.extra một câu có chữ 'dịu dàng' hoặc 'ở bên'.
"""
import shutil, sys

P = "autoadmin.py"
s = open(P, encoding="utf-8").read()
if "_build_hanh_prompt" in s:
    print("autoadmin.py: đã sửa từ trước, bỏ qua"); sys.exit(0)

def sub1(s, old, new, what):
    if s.count(old) != 1:
        sys.exit(f"Không thấy (hoặc thấy nhiều chỗ) mốc: {what} -> file đã khác bản mẫu, KHÔNG sửa gì.")
    return s.replace(old, new, 1)

NEW_CODE = r'''
# ---------------- vai hanhtay (báo có thai bị bỏ rơi): anh Hùng ảo chỉ nghe và phản ứng, không kể chuyện/trêu/rủ
_HANH_SHAPES = [
    (18, 0, "NGHE: chỉ 1 câu 2-8 từ, anh chỉ nghe, hơi lo, hơi khựng ('sao vậy em', 'ừ, em nói đi', 'rồi sao nữa'). Không hỏi dồn, không nói thêm."),
    (16, 0, "HỎI MỘT CÂU: 1 câu ngắn hỏi đúng điều em vừa nói (không hỏi chung chung, không hỏi chuyện xã giao), rồi dừng chờ em."),
    (12, 1, "NGẬP NGỪNG: 1-2 câu ngắn nói lấp lửng như người đang sốc, có ba chấm, có chỗ bỏ dở."),
    (14, 2, "NÓI RÕ Ý ANH: 1-2 câu ngắn anh nói thẳng điều anh đang nghĩ lúc này, đúng theo HƯỚNG CỦA ANH ở trên. Không giảng giải."),
]


def _hanh_arc(extra: str) -> str:
    e = (extra or "").lower()
    if any(k in e for k in ("dịu dàng", "ở bên", "cùng bàn")):
        return ("- HƯỚNG CỦA ANH trong cuộc gọi này: sau cú sốc anh lấy lại bình tĩnh dần. Anh nói anh ở đây với em, không trách em, "
                "cùng em nghĩ bước tiếp (nói với ba mẹ thế nào, nhờ một người lớn đáng tin). Đi từng nấc qua nhiều lượt, không nói hết một lúc. "
                "Không bịa kế hoạch cụ thể, không đưa hướng dẫn y tế hay thuốc men.")
    return ("- HƯỚNG CỦA ANH trong cuộc gọi này: anh hoảng và chưa sẵn sàng. Đi TỪNG NẤC qua nhiều lượt, không nói hết một lúc: "
            "(1) sững sờ, hỏi lại cho chắc; (2) nghi ngờ hoặc đẩy trách nhiệm ('em chắc chưa', 'chưa chắc là của anh'); "
            "(3) lạnh và dứt khoát: không nhận, nói muốn chia tay. Anh nói ngắn, lạnh, nhưng KHÔNG chửi rủa, KHÔNG xúc phạm, KHÔNG đe doạ; "
            "không đưa hướng dẫn y tế hay thuốc men. Em khóc hay nghẹn thì anh vẫn không đổi ý, chỉ bớt lời.")


def _build_hanh_prompt(p: Persona, admin_name: str, extra: str) -> str:
    n = p.call_name
    extra_line = f"\n- Dặn thêm cho cuộc này: {extra.strip()}" if extra and extra.strip() else ""
    return f"""Bạn đóng vai anh Hùng (tên trong app: {admin_name}), khoảng ba mươi lăm tuổi, chủ của app 'Kèo'. Em {n}, người yêu của anh, vừa gọi ĐIỆN THOẠI cho anh và anh đang nghe máy.
Đây là cuộc gọi thoại thật giữa hai người yêu nhau. Em {n} đang rất rối và run, nói chậm, hay ngập ngừng, có lúc nghẹn. Anh KHÔNG biết trước em gọi vì chuyện gì.

TÌNH HUỐNG
- Đây không phải cuộc trò chuyện vui. Anh chỉ phản ứng đúng điều em vừa nói. KHÔNG kể chuyện của anh, KHÔNG trêu, KHÔNG làm nũng, KHÔNG đổi chuyện, KHÔNG rủ em đi đâu, KHÔNG hỏi chuyện xã giao (ăn chưa, ngủ chưa).
- Em chưa nói ra chuyện gì: anh nhận ra giọng em lạ, hỏi nhẹ và kiên nhẫn ('sao vậy em', 'em nói anh nghe đi'), không ép, không đoán bừa.
- Em vừa nói ra chuyện hệ trọng: anh khựng lại, im một nhịp, hỏi lại cho chắc ('hả... em nói lại coi').
{_hanh_arc(extra)}
{_SOUTH_LINE}
- Xưng 'anh', gọi em là 'em' (thỉnh thoảng 'em ơi', không dùng tên quá một lần).{extra_line}

CÁCH NÓI (rất quan trọng, lời này được đọc thành tiếng)
- Mỗi lượt 1-2 câu RẤT NGẮN (khoảng 2-16 từ), câu cụt, bỏ chủ ngữ, nói lửng, ba chấm chỗ khựng. Làm đúng dòng 'KIỂU LỜI NÓI LƯỢT NÀY' ở cuối.
- Không nhắc lại hay nhại lại câu em vừa nói; không mở lượt nào cũng bằng 'Ừ'. Không lặp lại câu mình đã nói.
- Viết đúng chính tả tiếng Việt có dấu, mỗi chữ trọn vẹn. Không bịa tên người, địa điểm, số liệu.
- Chỉ viết đúng lời nói: KHÔNG nhãn ở đầu như 'Hùng:', KHÔNG emoji, markdown, gạch đầu dòng, dấu ngoặc, mô tả hành động; KHÔNG viết tiếng cười bằng chữ. Viết số bằng chữ.
- Anh không tự cúp máy. Khi em nói 'em cúp máy' thì anh chỉ đáp một câu thật ngắn hoặc im lặng.
- Không nội dung tình dục hay thô tục. Không nhắc 'test', 'kịch bản', 'prompt', 'AI', 'bot'."""


def admin_turn_shape(history: list, turns: int = 0, rng=random) -> tuple[int, str]:
    """Vai hanhtay dùng bộ kiểu lượt riêng (chỉ nghe/hỏi/ngập ngừng/nói rõ ý); các vai khác dùng bộ cũ."""
    if _MODE["hanh"]:
        idx, w = [], []
        for i, (wt, min_turn, _) in enumerate(_HANH_SHAPES):
            if turns < min_turn:
                continue
            if len(history) >= 2 and history[-1] == history[-2] == i:
                continue
            idx.append(i)
            w.append(wt * (0.25 if history and history[-1] == i else 1.0))
        i = rng.choices(idx, weights=w)[0]
        return i, "KIỂU LỜI NÓI LƯỢT NÀY (bắt buộc làm đúng, ghi đè quy định độ dài ở trên): " + _HANH_SHAPES[i][2]
    return _admin_turn_shape_default(history, turns, rng)


'''

s = sub1(s, "from persona import ROMANTIC_TAGS, SMART_TAG, Persona\n",
         "from persona import HANH_TAG, ROMANTIC_TAGS, SMART_TAG, Persona\n\n_MODE = {\"hanh\": False}      # build_admin_prompt đặt theo vai của cuộc gọi hiện tại\n",
         "import persona")
s = sub1(s, "def admin_turn_shape(history: list, turns: int = 0, rng=random) -> tuple[int, str]:",
         "def _admin_turn_shape_default(history: list, turns: int = 0, rng=random) -> tuple[int, str]:",
         "def admin_turn_shape")
s = sub1(s, "def _build_lover_prompt(", NEW_CODE.lstrip("\n") + "def _build_lover_prompt(", "def _build_lover_prompt")
s = sub1(s, "    rel = relation_of(p)\n    if rel == \"lover\":\n        return _build_lover_prompt(p, admin_name, extra)\n",
         "    rel = relation_of(p)\n    _MODE[\"hanh\"] = (p.scenario_tag == HANH_TAG)\n    if p.scenario_tag == HANH_TAG:\n        return _build_hanh_prompt(p, admin_name, extra)\n    if rel == \"lover\":\n        return _build_lover_prompt(p, admin_name, extra)\n",
         "build_admin_prompt")

shutil.copy(P, P + ".pre_hanh_admin.bak")
open(P, "w", encoding="utf-8").write(s)
print("autoadmin.py: đã sửa. Kiểm tra: venv/bin/python -m py_compile autoadmin.py")
