"""Tạo 'nhân vật' cho mỗi cuộc gọi: tên, giọng, tính cách, lý do gọi — ngẫu nhiên nhưng hợp lý."""
import hashlib
import random
import unicodedata
from dataclasses import dataclass

# (mục tiêu cuộc gọi — LLM tự diễn đạt lại, không đọc nguyên văn; tag ngắn để chọn bằng --scenario)
# Nhân vật là người quen của anh Hùng gọi điện: chuyện app Kèo chỉ là một phần, còn lại là chuyện đời sống thường ngày.
SCENARIOS = [
    # ---- Kèo / app ----
    ("Rủ anh Hùng đi nhậu/ăn uống tối nay, hỏi anh có rảnh không và gợi ý khu vực.", "rủ đi nhậu tối nay"),
    ("Hỏi cách tìm kèo gần mình trong app: bật 'đang tìm kèo' rồi mà thấy ít người quá.", "hỏi cách tìm kèo gần nhà"),
    ("Kể một lỗi nhỏ mình gặp khi dùng app (vd: lúc gọi video bị giật, hoặc không thấy bạn bè trên bản đồ) và hỏi anh Hùng có biết lỗi này chưa.", "báo lỗi app"),
    ("Xin vào một kèo đang đầy chỗ, nhờ anh Hùng giúp xem còn slot không.", "xin slot kèo"),
    ("Hỏi anh Hùng gợi ý một quán nhậu/karaoke/bar ổn áp ở quận mình để rủ nhóm bạn đi.", "hỏi gợi ý quán"),
    ("Góp ý một tính năng mong muốn cho app (vd: chia tiền sau buổi nhậu, nhắc giờ hẹn), nói chuyện thân thiện.", "góp ý tính năng"),
    ("Gọi làm quen, hỏi thăm anh Hùng dạo này thế nào, kể chuyện vừa đi chơi với nhóm bạn hôm qua vui ra sao.", "hỏi thăm kể chuyện kèo"),
    ("Hỏi anh Hùng nếu tối nay có kèo thì em xin vô trễ khoảng nửa tiếng được không, vì còn kẹt chút việc.", "báo tới trễ"),
    # ---- Ăn uống ----
    ("Hỏi anh Hùng hay ăn sáng món gì, em đang chán bún phở muốn đổi vị.", "hỏi ăn sáng"),
    ("Hỏi anh Hùng có biết cách nấu một món đơn giản (canh chua, thịt kho, cá kho) sao cho ngon không, em đang tập nấu ăn.", "hỏi cách nấu ăn"),
    ("Hỏi anh Hùng quán cà phê nào yên tĩnh, wifi ổn để ngồi làm việc cả buổi.", "hỏi quán cà phê làm việc"),
    ("Kể món bình dân em vừa ăn thấy ngon bất ngờ, hỏi anh đã thử chưa.", "kể món mới ăn"),
    # ---- Du lịch / đi chơi ----
    ("Hỏi kinh nghiệm đi chơi xa (Đà Lạt, Vũng Tàu, Phú Quốc hoặc Đà Nẵng, chọn một) dịp cuối tuần hay lễ: đi mấy ngày vừa, tháng nào đẹp.", "hỏi kinh nghiệm đi chơi xa"),
    ("Đang phân vân đi chơi xa bằng xe khách, xe máy hay máy bay, hỏi ý anh Hùng.", "hỏi đi chơi xa bằng gì"),
    ("Dịp lễ hoặc Tết sắp tới em chưa biết làm gì, hỏi anh Hùng định đi đâu hay ở nhà nghỉ ngơi.", "hỏi kế hoạch dịp lễ"),
    ("Hỏi anh Hùng có biết sự kiện, hội chợ hay chợ đêm nào cuối tuần này để rủ nhóm đi chơi không.", "hỏi chỗ chơi cuối tuần"),
    # ---- Công việc / học ----
    ("Than nhẹ chuyện công việc dạo này (deadline dồn, sếp giao nhiều), muốn nói chuyện với anh cho nhẹ đầu.", "xả stress chuyện công việc"),
    ("Sắp đi phỏng vấn xin việc, hỏi anh Hùng có mẹo chuẩn bị hay cách nói chuyện cho bớt run không.", "hỏi mẹo phỏng vấn"),
    ("Đang muốn học lại tiếng Anh, hỏi anh Hùng học bằng app, học lớp hay xem phim phụ đề thì dễ hơn.", "hỏi học tiếng Anh"),
    ("Phân vân học thêm một kỹ năng (Excel, thiết kế, lập trình cơ bản), hỏi ý anh Hùng nên bắt đầu từ đâu.", "hỏi học thêm kỹ năng"),
    ("Hỏi anh Hùng có app hay cách ghi chép chi tiêu hằng tháng nào đơn giản, vì cuối tháng em hay hụt.", "hỏi cách ghi chi tiêu"),
    # ---- Sức khỏe nhẹ / thể thao ----
    ("Rủ anh Hùng cuối tuần đi đá bóng, đánh cầu lông hoặc chạy bộ buổi sáng, hỏi anh rảnh buổi nào.", "rủ chơi thể thao"),
    ("Dạo này em ngủ không ngon, hỏi anh Hùng có thói quen hay mẹo gì giúp ngủ sớm không (chỉ nói kinh nghiệm bạn bè).", "hỏi mẹo ngủ"),
    ("Mới tập gym hoặc yoga được vài tuần, hỏi anh Hùng có tập không, tập kiểu nào để khỏi nản.", "hỏi chuyện tập luyện"),
    # ---- Giải trí ----
    ("Hỏi anh Hùng dạo này có phim hoặc series nào đáng xem không, em đang hết thứ để coi.", "hỏi phim hay"),
    ("Em đang nghiện một bài nhạc chill dạo này, hỏi anh Hùng hay nghe loại nhạc gì khi đi làm.", "hỏi chuyện nghe nhạc"),
    ("Rủ anh Hùng chơi game giải trí cuối tuần (game điện thoại hoặc máy tính), hỏi anh có chơi không.", "rủ chơi game"),
    # ---- Mua sắm / công nghệ ----
    ("Phân vân đổi điện thoại hoặc mua laptop mới, hỏi anh Hùng đang xài máy gì thấy ổn.", "hỏi mua đồ công nghệ"),
    ("Hỏi anh Hùng có mẹo săn sale hay mua đồ online khỏi bị hớ không.", "hỏi mẹo săn sale"),
    # ---- Xe cộ / đi lại ----
    ("Than chuyện kẹt xe hoặc ngập nước dạo này, hỏi anh Hùng thường đi đường nào để né.", "than chuyện kẹt xe"),
    ("Xe máy của em sắp tới hạn bảo dưỡng, hỏi anh Hùng thường thay nhớt hay sửa xe kiểu nào cho yên tâm (không nhắc tên tiệm cụ thể).", "hỏi chuyện bảo dưỡng xe"),
    # ---- Nhà cửa / đời sống ----
    ("Đang tính dọn chỗ ở mới, hỏi anh Hùng có kinh nghiệm tìm phòng hay căn hộ khu nào ổn không.", "hỏi tìm chỗ ở"),
    ("Đang tính nuôi mèo hoặc chó, hỏi anh Hùng đã nuôi bao giờ chưa, nên bắt đầu thế nào.", "hỏi chuyện nuôi thú cưng"),
    ("Cuối tuần định dọn nhà tổng vệ sinh, hỏi anh Hùng có mẹo nào cho đỡ mệt.", "hỏi mẹo dọn nhà"),
    # ---- Xã hội / gia đình ----
    ("Sắp sinh nhật một người bạn thân, hỏi anh Hùng nên tặng gì cho hợp, ngân sách vừa phải.", "hỏi chọn quà"),
    ("Được mời đám cưới một người bạn, hỏi anh Hùng thường đi với ai, mặc gì, đến sớm hay trễ cho phải phép.", "hỏi chuyện đi đám cưới"),
    ("Hỏi ý anh Hùng về buổi họp lớp hoặc họp nhóm cuối tháng, bàn xem chọn chỗ nào hợp.", "bàn họp lớp"),
    ("Gọi hỏi thăm nhân dịp lễ gần đây hoặc sắp tới, hỏi anh Hùng định đón lễ thế nào.", "hỏi thăm dịp lễ"),
    # ---- Tâm sự / tán gẫu ----
    ("Kể một chuyện buồn cười nhỏ vừa xảy ra với em (lạc đường, nhắn nhầm người, đặt nhầm món) cho anh Hùng nghe cho vui.", "kể chuyện buồn cười"),
    ("Hỏi thăm anh Hùng dạo này khỏe không, bận gì, rồi kể vài chuyện vặt của mình.", "hỏi thăm sức khỏe"),
    ("Hôm nay em tan ca muộn và hơi mệt, gọi nói chuyện với anh Hùng một chút cho đỡ buồn.", "tâm sự chuyện mệt"),
]

# Kịch bản vốn đã là tán gẫu: bỏ bước 'chuyển chủ đề', vào chuyện luôn.
CHAT_TAGS = {
    "hỏi thăm kể chuyện kèo", "hỏi ăn sáng", "kể món mới ăn", "xả stress chuyện công việc",
    "hỏi mẹo ngủ", "hỏi phim hay", "hỏi chuyện nghe nhạc", "than chuyện kẹt xe",
    "hỏi chuyện nuôi thú cưng", "hỏi mẹo dọn nhà", "hỏi thăm dịp lễ", "kể chuyện buồn cười",
    "hỏi thăm sức khỏe", "tâm sự chuyện mệt",
}
# Chỉ kịch bản rủ rê/hẹn giờ mới có 'chi tiết cố định' (số người, giờ hẹn); các kịch bản khác không bị nhồi giờ giấc lạc đề.
FACTS_TAGS = {"rủ đi nhậu tối nay", "xin slot kèo", "hỏi gợi ý quán", "báo tới trễ", "bàn họp lớp"}

# Câu mở máy gợi ý (đa dạng để cuộc nào cũng không bắt đầu y hệt; LLM tự diễn đạt lại)
OPENERS = [
    "Alo, anh Hùng hả? Em nè.",
    "A lô anh Hùng ơi, em đây.",
    "Alo anh Hùng, anh nghe rõ em không?",
    "Dạ alo anh Hùng, em nè.",
    "Anh Hùng ơi, em nè, anh đang rảnh không?",
    "Alo, em nè anh Hùng, anh nghe được hông?",
    "Ơ anh Hùng, em nè, em gọi tí xíu thôi.",
    "Alo anh, em đây, anh Hùng nghe máy chưa?",
]

MOODS = [
    "vui vẻ, nói nhanh, giọng tươi",
    "hơi ngại ngùng, ngập ngừng nhẹ, lịch sự",
    "mới tan ca nên hơi mệt nhưng thân thiện",
    "hào hứng, hay dùng từ cảm thán như 'trời ơi', 'dữ vậy'",
    "bình tĩnh, nói chậm rãi, hơi hài hước",
    "đang đi ngoài đường nên hơi vội, nói gọn",
    "đang rảnh rỗi nằm nhà, nói chuyện thong thả, hay cười",
    "hơi lo lo vì có chuyện đang phân vân, nhưng vẫn dễ chịu",
]

# Toàn bộ nói giọng miền Nam: giọng đọc (TTS) là giọng Nam nên chữ miền Bắc đọc lên nghe lớ.
REGIONS = [
    ("miền Nam", "dùng từ miền Nam tự nhiên: 'nghen', 'hen', 'á', 'nè', 'dị', 'hông', 'ổng/bả' khi cần"),
    ("miền Nam", "dùng từ miền Nam tự nhiên: 'nghen', 'hen', 'á', 'nè', 'dị', 'hông'"),
    ("miền Nam", "giọng Sài Gòn nhẹ nhàng, ít từ lóng: 'nha', 'nè', 'á', 'hông', 'dạ' vừa phải"),
]

JOBS = ["nhân viên văn phòng", "làm kế toán", "dân IT", "làm marketing", "sinh viên năm cuối", "làm sale",
        "làm ở quán cà phê", "thiết kế đồ họa", "nhân viên ngân hàng", "tự kinh doanh nhỏ online",
        "giáo viên", "làm ở công ty logistic", "điều dưỡng", "làm nhân sự", "chạy freelance"]
DISTRICTS = ["Bình Thạnh", "quận 3", "Gò Vấp", "Tân Bình", "quận 7", "Thủ Đức", "quận 10", "Phú Nhuận", "quận 1", "Tân Phú"]
GROUPS = ["nhóm bạn đại học", "mấy đứa đồng nghiệp", "hội bạn thân tám người", "nhóm bạn chơi cùng hồi cấp ba",
          "hội anh em trong team", "mấy đứa bạn cùng phòng cũ"]
RECENT = ["tuần trước vừa đi một kèo hải sản, vui mà xỉn quá trời", "hôm qua mới đi karaoke tới khuya, giờ còn khàn giọng",
          "cuối tuần rồi nhóm kéo nhau đi quán nướng, chia tiền loạn cả lên", "tuần này công việc dồn dập nên đang muốn xả stress",
          "mới có một đứa bạn trong nhóm sắp cưới nên cả hội đang tính tụ tập", "cuối tháng rồi nên đang tính kiếm chỗ nào ăn ngon mà không quá mắc",
          "mới tập nấu ăn được vài tuần, có món cháy đen mà vẫn ráng ăn hết",
          "dạo này hay thức khuya xem phim nên sáng nào cũng ngáp dài",
          "mới đổi chỗ làm nên còn đang làm quen đường đi và đồng nghiệp",
          "cuối tuần rồi đi chơi xa về mà vẫn chưa lại sức, người còn rã rời",
          "mới bị trời mưa bất chợt ướt như chuột lột lúc đang đi làm về",
          "đang tiết kiệm để cuối năm đi chơi xa một chuyến"]

# Dùng khi display_name chỉ là username viết liền (vd "thuygiang") -> chọn tên gọi tự nhiên, ổn định theo username.
# "Nét duyên" riêng của từng nhân vật: thân thiện, tinh tế, lễ phép — không tán tỉnh, không sến.
CHARMS = [
    "dí dỏm, hay đùa nhẹ về chính mình (tự trào) rồi nói tiếp tự nhiên",
    "ngọt ngào, nói năng nhẹ nhàng, thỉnh thoảng khen khéo anh Hùng một câu chân thành",
    "tinh nghịch, thích trêu nhẹ anh Hùng nhưng luôn lễ phép",
    "hóm hỉnh, hay ví von vui kiểu dân gian ('đông như đi chợ Tết', 'nhanh như chớp')",
    "dễ thương, hay nói giảm nói tránh, xin lỗi đáng yêu, cảm ơn có duyên",
    "điềm đạm mà có duyên, hay chen một câu bông đùa khô khan rất tỉnh",
]

NAMES_F = ["Linh", "Ngọc", "Hương", "Mai", "Trang", "Thu", "Hoa", "Nhung", "Yến", "My", "Vy", "Thảo",
           "Phương", "Hân", "Ngân", "Trinh", "Quỳnh", "Diệp", "Nga", "Uyên", "Chi", "Lan"]
NAMES_M = ["Hùng", "Nam", "Minh", "Tuấn", "Long", "Đức", "Khoa", "Huy", "Đạt", "Phong", "Quang", "Sơn",
           "Tài", "Trung", "Bình", "Thanh", "Bảo", "Hiếu", "Kiên", "Toàn", "Vinh", "Dũng"]

def _fold(s: str) -> str:
    """Bỏ dấu + hạ chữ thường: 'Hoàng Đức' -> 'hoang duc'."""
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Điểm: 3 = chắc chắn, 1 = nhập nhằng (tên dùng cho cả hai giới). Cố ý KHÔNG có 'anh' (Tuấn Anh nam, Ngọc Anh nữ).
_F = {"linh": 2, "ngoc": 3, "huong": 3, "lan": 3, "mai": 3, "trang": 3, "thu": 3, "thuy": 3, "hoa": 3,
      "nhung": 3, "yen": 3, "my": 3, "vy": 3, "thao": 3, "phuong": 2, "han": 3, "ngan": 3, "trinh": 3,
      "quynh": 3, "diep": 3, "nga": 3, "uyen": 3, "chi": 3, "kim": 1, "giang": 2, "ha": 2, "hanh": 3,
      "oanh": 3, "tram": 3, "nhi": 3, "tien": 2, "xuan": 1, "lien": 3, "loan": 3, "huyen": 3,
      "ly": 2, "hang": 3, "nhu": 3, "tuyen": 2, "thuong": 2}
_M = {"hung": 3, "nam": 3, "minh": 1, "tuan": 3, "long": 3, "duc": 3, "khoa": 3, "huy": 3, "dat": 3,
      "phong": 3, "quang": 3, "son": 3, "tai": 3, "trung": 3, "binh": 2, "thanh": 1, "bao": 2, "hieu": 3,
      "kien": 3, "toan": 3, "vinh": 3, "dung": 1, "cuong": 3, "dong": 3, "hai": 2, "hoang": 1, "khanh": 1,
      "lam": 2, "loc": 3, "nghia": 3, "nhan": 3, "phuc": 3, "tam": 1, "thang": 3, "thien": 3, "tin": 3,
      "tu": 2, "viet": 3, "tung": 3, "dai": 3, "dan": 3}
# Tên Tây hay dùng làm username/nickname
_F.update({"linda": 3, "anna": 3, "lisa": 3, "mary": 3, "jenny": 3, "jessica": 3, "emily": 3, "amy": 3, "emma": 3,
           "sophie": 3, "ruby": 3, "lily": 3, "jolie": 3, "angela": 3, "christina": 3, "kate": 3, "alice": 3,
           "ella": 3, "mia": 3, "nana": 3, "bella": 3, "candy": 3, "kitty": 3, "sunny": 1})
_M.update({"vincent": 3, "david": 3, "john": 3, "michael": 3, "kevin": 3, "peter": 3, "tony": 3, "jack": 3,
           "james": 3, "tom": 3, "leo": 3, "henry": 3, "andy": 3, "steven": 3, "richard": 3, "daniel": 3,
           "william": 3, "alex": 1, "ken": 3, "ben": 3, "max": 3, "sam": 1, "jason": 3, "justin": 3, "bobby": 3})
_SURNAMES = ("nguyen", "tran", "le", "pham", "hoang", "huynh", "phan", "vu", "vo", "dang", "bui", "do", "ho",
             "ngo", "duong", "ly", "truong", "dinh", "doan", "luong", "trinh")
_MID_F, _MID_M = {"thi"}, {"van", "duc", "huu", "quoc", "gia"}


def _score_word(w: str, weight: float = 1.0) -> tuple[float, float]:
    return _F.get(w, 0) * weight, _M.get(w, 0) * weight


def _score_compact(chunk: str) -> tuple[float, float]:
    """Username viết liền ('namnguyen', 'hoangnam', 'trangkim'): bóc họ ở đầu/cuối rồi so tên NGUYÊN TỪ.
    Không khớp chuỗi con tuỳ tiện nữa (trước đây 'hoang' dính 'hoa', 'thanh' dính 'anh' -> nam bị đoán thành nữ)."""
    if chunk in _F or chunk in _M:
        return _score_word(chunk, 1.0)
    for s in sorted(_SURNAMES, key=len, reverse=True):
        if chunk.startswith(s) and len(chunk) > len(s):
            rest = chunk[len(s):]
            if rest in _F or rest in _M:
                return _score_word(rest, 1.0)
        if chunk.endswith(s) and len(chunk) > len(s):
            rest = chunk[:-len(s)]
            if rest in _F or rest in _M:
                return _score_word(rest, 1.0)
    # Tên dính ở đầu/cuối username: ('trangkim', 'thuygiang', 'nhatnam'). Tên >=4 chữ khớp ở đầu hoặc cuối;
    # tên 3 chữ chỉ tính khi nằm CUỐI (tên gọi thường đứng sau). Mỗi đầu lấy khớp dài nhất, điểm nửa.
    f = m = 0.0
    for edge in ("start", "end"):
        best = (0.0, 0.0, 0)
        for table, idx in ((_F, 0), (_M, 1)):
            for name, sc in table.items():
                if len(name) < 3 or len(name) == len(chunk):
                    continue
                if len(name) == 3 and (edge == "start" or len(chunk) - 3 < 3):
                    continue
                hit = chunk.startswith(name) if edge == "start" else chunk.endswith(name)
                if hit and len(name) > best[2]:
                    best = (sc * 0.5 if idx == 0 else 0.0, sc * 0.5 if idx == 1 else 0.0, len(name))
        f, m = f + best[0], m + best[1]
    return f, m


def _norm_gender(v) -> str | None:
    s = _fold(str(v or "")).strip()
    if s in ("female", "f", "nu", "woman", "girl", "2"):
        return "female"
    if s in ("male", "m", "nam", "man", "boy", "1"):
        return "male"
    return None


def detect_gender(username: str, display_name: str, forced=None) -> tuple[str, str]:
    """Trả (gender, lý do). Ưu tiên: forced -> tên hiển thị (từ cuối = tên gọi) -> username -> hash cố định."""
    g = _norm_gender(forced)
    if g:
        return g, "cấu hình/hồ sơ"
    f = m = 0.0
    words = _fold("".join(c if c.isalpha() or c == " " else " " for c in (display_name or ""))).split()
    if words:
        for w in words[:-1]:
            if w in _MID_F:
                f += 4
            elif w in _MID_M:
                m += 2
        sf, sm = _score_word(words[-1], 2.0)          # tên gọi nằm ở cuối
        f, m = f + sf, m + sm
        if len(words) == 1:
            sf, sm = _score_compact(words[0])
            f, m = f + sf, m + sm
    for chunk in _fold(username or "").replace("_", " ").replace(".", " ").replace("-", " ").split():
        chunk = "".join(c for c in chunk if c.isalpha())
        if chunk:
            sf, sm = _score_compact(chunk)
            f, m = f + sf * 0.7, m + sm * 0.7
    if f != m and max(f, m) >= 1:
        return ("female" if f > m else "male"), f"theo tên (nữ {f:.1f} / nam {m:.1f})"
    h = int(hashlib.md5((username or "x").encode()).hexdigest(), 16)
    return ("female" if h % 2 else "male"), "KHÔNG đoán được từ tên -> chọn ngẫu nhiên cố định (nên thêm gender vào account)"


@dataclass
class Persona:
    username: str
    display_name: str
    gender: str          # 'female' | 'male'
    mood: str
    region: str
    region_style: str
    goal: str
    scenario_tag: str
    age: int
    backstory: str = ""
    nick: str = ""
    tts_rate: str = ""
    tts_pitch: str = ""      # cao độ giọng riêng của từng user (cố định theo username), vd "+8Hz"
    charm: str = ""
    facts: str = ""
    gender_why: str = ""
    opener: str = ""         # câu mở máy gợi ý của cuộc gọi này
    gemini_voice: str = ""   # ghi đè giọng Gemini cho user này (account.gemini_voice), rỗng = tự chọn theo username

    @property
    def call_name(self) -> str:
        """Tên tự xưng trong lời nói (lấy từ cuối display_name, bỏ số/ký tự lạ)."""
        if self.nick:
            return self.nick
        parts = [p for p in "".join(c if c.isalpha() or c == " " else " " for c in self.display_name).split() if p]
        return parts[-1].capitalize() if parts else "em"


def guess_gender(username: str, display_name: str, forced=None) -> str:
    return detect_gender(username, display_name, forced)[0]


def make_persona(account: dict, display_name: str, rng: random.Random | None = None,
                 scenario_tag: str | None = None) -> Persona:
    rng = rng or random.Random()
    username = account["username"]
    goal, tag = None, None
    pool = [s for s in SCENARIOS if scenario_tag in (None, s[1])] or SCENARIOS
    goal, tag = rng.choice(pool)
    region, style = rng.choice(REGIONS)
    shown = display_name or username
    words = [w for w in "".join(c if c.isalpha() or c == " " else " " for c in shown).split() if w]
    gender, gender_why = detect_gender(username, display_name or "", account.get("gender"))
    nick = ""
    mood = rng.choice(MOODS)
    # Mỗi user 1 "chất giọng" riêng cố định theo username (cao độ + tốc độ nền), tâm trạng mỗi cuộc chỉ nhích nhẹ tốc độ.
    h = int(hashlib.md5(username.encode()).hexdigest(), 16)
    if gender == "female":
        pitch_hz = (h % 27) - 14            # -14..+12 Hz
    else:
        pitch_hz = ((h // 27) % 27) - 17    # -17..+9 Hz (nam thiên về trầm)
    base_rate = ((h // 729) % 11) - 3       # -3..+7 %
    if "nhanh" in mood or "vội" in mood:
        base_rate += 6
    elif "chậm" in mood:
        base_rate -= 4
    base_rate = max(-8, min(18, base_rate))
    tts_rate = f"{base_rate:+d}%"
    tts_pitch = f"{pitch_hz:+d}Hz"
    if len(words) < 2:   # chỉ 1 từ (username viết liền) -> đặt tên gọi tự nhiên, cố định theo username
        pool = NAMES_F if gender == "female" else NAMES_M
        nick = pool[int(hashlib.md5(username.encode()).hexdigest(), 16) % len(pool)]
    return Persona(
        username=username,
        display_name=display_name or username,
        gender=gender,
        gender_why=gender_why,
        gemini_voice=str(account.get("gemini_voice") or ""),
        nick=nick,
        mood=mood,
        tts_rate=tts_rate,
        tts_pitch=tts_pitch,
        charm=rng.choice(CHARMS),
        facts=(f"nhóm em đi {rng.randint(2, 4)} người; giờ em muốn hẹn: {rng.choice(['7 giờ tối', '7 rưỡi tối', '8 giờ tối'])}"
               if tag in FACTS_TAGS else ""),
        opener=rng.choice(OPENERS),
        region=region,
        region_style=style,
        goal=goal,
        scenario_tag=tag,
        age=rng.randint(20, 34),
        backstory=(f"{rng.choice(JOBS)}, ở {rng.choice(DISTRICTS)}, hay đi chơi với {rng.choice(GROUPS)}; "
                   f"gần đây: {rng.choice(RECENT)}."),
    )