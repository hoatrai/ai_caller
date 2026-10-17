"""Sửa câu chào kết thúc của vai người yêu cho thân mật (không còn 'không làm phiền anh nữa nha, chào anh').
Chạy trong /root/ai_caller:   venv/bin/python fix_goodbye.py      (tự backup *.pre_goodbye.bak, chạy lại nhiều lần vẫn an toàn)
Sửa 3 chỗ: session.py (câu cứng khi hết giờ + lời dặn khi anh muốn cúp máy), brain.py (nhận diện lời chào thân mật để thẻ cúp máy hoạt động)."""
import re, shutil, sys

def load(p):
    return open(p, encoding="utf-8").read()

def save(p, s):
    shutil.copy(p, p + ".pre_goodbye.bak")
    open(p, "w", encoding="utf-8").write(s)

# ---------------- session.py
s = load("session.py"); orig = s
LOVER = '''["Thôi em cúp nha, thương anh. Mai mình nói chuyện tiếp ha.",
                     "Em phải đi rồi nè... nhớ anh nghen. Ngủ ngon, mai gọi lại.",
                     "Ui hết giờ rồi. Thương anh nhiều, bye bye nghen."]'''
if "Thôi em cúp nha, thương anh" not in s:
    pat = re.compile(r'await self\.say\(random\.choice\(\[\s*"Dạ thôi em không làm phiền anh nữa nha, chào anh\.",\s*"Dạ vậy nha anh, em cúp máy nghen, chào anh\.",\s*\]\)\)')
    m = pat.search(s)
    if not m: sys.exit("session.py: không thấy đoạn câu cứng khi hết giờ (file đã khác bản mẫu?)")
    new = ('await self.say(random.choice(' + LOVER + ' if romantic else [\n'
           '                    "Dạ thôi em không làm phiền anh nữa nha, chào anh.",\n'
           '                    "Dạ vậy nha anh, em cúp máy nghen, chào anh.",\n'
           '                ]))')
    s = s[:m.start()] + new + s[m.end():]
OLD = "hãy chào tạm biệt thật dịu dàng, ngắn gọn (không hỏi thêm gì) rồi THÊM thẻ cúp máy ở cuối câu chào."
NEW = ("chào tạm biệt kiểu NGƯỜI YÊU, 1-2 câu ngắn, ấm và hơi lưu luyến: dặn nhẹ một câu (ngủ ngon / nghỉ ngơi / đi đường cẩn thận), hẹn nói chuyện tiếp, nói 'thương anh'. "
       "TUYỆT ĐỐI KHÔNG dùng 'không làm phiền', 'chào anh', 'xin phép', giọng lịch sự xã giao. Không hỏi thêm gì. Rồi THÊM thẻ cúp máy ở cuối câu chào.")
if OLD in s:
    s = s.replace(OLD, NEW)
elif "kiểu NGƯỜI YÊU, 1-2 câu ngắn" not in s:
    sys.exit("session.py: không thấy end_hint cũ")
if s != orig:
    save("session.py", s); print("session.py: đã sửa")
else:
    print("session.py: đã sửa từ trước")

# ---------------- brain.py
b = load("brain.py"); borig = b
if "ngủ ngon" not in b.split("def is_farewell")[0].split("_FAREWELL = ")[-1]:
    old = 'r"(chào anh|không làm phiền|cúp máy|tạm biệt|hẹn gặp lại|\\bbye\\b)"'
    if old not in b: sys.exit("brain.py: không thấy _FAREWELL (file đã khác bản mẫu?)")
    new = ('r"(chào anh|không làm phiền|cúp máy|tạm biệt|hẹn gặp lại|\\bbye\\b|ngủ ngon|ngủ sớm nha|em cúp|'
           'nói chuyện (?:tiếp|sau)|mai (?:mình )?(?:nói|gọi|gặp)|hôn anh|ôm anh một cái)"')
    b = b.replace(old, new)
if b != borig:
    save("brain.py", b); print("brain.py: đã sửa")
else:
    print("brain.py: đã sửa từ trước")
print("Xong. Chạy: venv/bin/python -m py_compile session.py brain.py && systemctl restart nhau-ai-caller")
