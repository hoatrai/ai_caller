"""Tạo 'nhân vật' cho mỗi cuộc gọi: tên, giọng, tính cách, lý do gọi — ngẫu nhiên nhưng hợp lý."""
import hashlib
import random
from dataclasses import dataclass

# (mục tiêu cuộc gọi, câu gợi ý mở đầu — LLM tự diễn đạt lại, không đọc nguyên văn)
SCENARIOS = [
    ("Rủ anh Hùng đi nhậu/ăn uống tối nay, hỏi anh có rảnh không và gợi ý khu vực.",
     "rủ đi nhậu tối nay"),
    ("Hỏi cách tìm kèo gần mình trong app: bật 'đang tìm kèo' rồi mà thấy ít người quá.",
     "hỏi cách tìm kèo gần nhà"),
    ("Báo một lỗi nhỏ gặp phải khi dùng app (vd: lúc gọi video bị giật, hoặc không thấy bạn bè trên bản đồ) và hỏi xem có sửa chưa.",
     "báo lỗi app"),
    ("Xin vào một kèo đang đầy chỗ, nhờ anh Hùng giúp xem còn slot không.",
     "xin slot kèo"),
    ("Hỏi anh Hùng gợi ý một quán nhậu/karaoke/bar ổn áp ở quận mình để rủ nhóm bạn đi.",
     "hỏi gợi ý quán"),
    ("Góp ý một tính năng mong muốn cho app (vd: chia tiền sau buổi nhậu, nhắc giờ hẹn), nói chuyện thân thiện.",
     "góp ý tính năng"),
    ("Gọi làm quen, hỏi thăm anh Hùng dạo này thế nào, kể chuyện vừa đi kèo hôm qua vui ra sao.",
     "hỏi thăm kể chuyện kèo"),
    ("Báo là mình sẽ tới trễ một kèo mà anh Hùng cũng có tham gia, xin lỗi và hỏi mọi người đã đến chưa.",
     "báo tới trễ"),
]

MOODS = [
    "vui vẻ, nói nhanh, hay cười 'haha'",
    "hơi ngại ngùng, ngập ngừng nhẹ, lịch sự",
    "mới tan ca nên hơi mệt nhưng thân thiện",
    "hào hứng, hay dùng từ cảm thán như 'trời ơi', 'dữ vậy'",
    "bình tĩnh, nói chậm rãi, hơi hài hước",
    "đang đi ngoài đường nên hơi vội, nói gọn",
]

REGIONS = [
    ("miền Nam", "dùng từ miền Nam tự nhiên: 'nghen', 'hen', 'á', 'nè', 'dị', 'hông', 'ổng/bả' khi cần"),
    ("miền Nam", "dùng từ miền Nam tự nhiên: 'nghen', 'hen', 'á', 'nè', 'dị', 'hông'"),
    ("miền Bắc", "dùng từ miền Bắc tự nhiên: 'nhỉ', 'nhé', 'ạ', 'thế', 'vâng'"),
]

JOBS = ["nhân viên văn phòng", "làm kế toán", "dân IT", "làm marketing", "sinh viên năm cuối", "làm sale",
        "làm ở quán cà phê", "thiết kế đồ họa", "nhân viên ngân hàng", "tự kinh doanh nhỏ online"]
DISTRICTS = ["Bình Thạnh", "quận 3", "Gò Vấp", "Tân Bình", "quận 7", "Thủ Đức", "quận 10", "Phú Nhuận", "quận 1", "Tân Phú"]
GROUPS = ["nhóm bạn đại học", "mấy đứa đồng nghiệp", "hội bạn thân tám người", "nhóm bạn chơi cùng hồi cấp ba",
          "hội anh em trong team", "mấy đứa bạn cùng phòng cũ"]
RECENT = ["tuần trước vừa đi một kèo hải sản, vui mà xỉn quá trời", "hôm qua mới đi karaoke tới khuya, giờ còn khàn giọng",
          "cuối tuần rồi nhóm kéo nhau đi quán nướng, chia tiền loạn cả lên", "tuần này công việc dồn dập nên đang muốn xả stress",
          "mới có một đứa bạn trong nhóm sắp cưới nên cả hội đang tính tụ tập", "cuối tháng rồi nên đang tính kiếm chỗ nào ăn ngon mà không quá mắc"]

# Dùng khi display_name chỉ là username viết liền (vd "thuygiang") -> chọn tên gọi tự nhiên, ổn định theo username.
# "Nét duyên" riêng của từng nhân vật: thân thiện, tinh tế, lễ phép — không tán tỉnh, không sến.
CHARMS = [
    "dí dỏm, hay đùa nhẹ về chính mình (tự trào) rồi cười 'hihi'",
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

FEMALE_HINTS = ("anh", "linh", "ngoc", "ngọc", "huong", "hương", "lan", "mai", "trang", "thu", "hoa",
                "nhung", "yen", "yến", "my", "vy", "thao", "thảo", "phuong", "phương", "han", "hân",
                "ngan", "ngân", "trinh", "quynh", "quỳnh", "diep", "diệp", "nga", "uyen", "uyên", "chi")
MALE_HINTS = ("hung", "hùng", "nam", "minh", "tuan", "tuấn", "long", "duc", "đức", "khoa", "huy", "dat",
              "đạt", "phong", "quang", "son", "sơn", "tai", "tài", "trung", "binh", "bình", "thanh",
              "bao", "bảo", "hieu", "hiếu", "kien", "kiên", "toan", "toàn", "vinh", "dung", "dũng")


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
    charm: str = ""
    facts: str = ""

    @property
    def call_name(self) -> str:
        """Tên tự xưng trong lời nói (lấy từ cuối display_name, bỏ số/ký tự lạ)."""
        if self.nick:
            return self.nick
        parts = [p for p in "".join(c if c.isalpha() or c == " " else " " for c in self.display_name).split() if p]
        return parts[-1].capitalize() if parts else "em"


def guess_gender(username: str, display_name: str, forced: str | None = None) -> str:
    if forced in ("female", "male"):
        return forced
    name = f"{display_name} {username}".lower()
    f = sum(h in name for h in FEMALE_HINTS)
    m = sum(h in name for h in MALE_HINTS)
    if f != m:
        return "female" if f > m else "male"
    # ổn định theo username (cùng 1 user luôn cùng giọng)
    return "female" if int(hashlib.md5(username.encode()).hexdigest(), 16) % 2 else "male"


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
    gender = guess_gender(username, shown if display_name else "", account.get("gender"))
    nick = ""
    mood = rng.choice(MOODS)
    if "nhanh" in mood or "vội" in mood:
        tts_rate = "+12%"
    elif "chậm" in mood:
        tts_rate = "-2%"
    else:
        tts_rate = rng.choice(["+4%", "+8%"])
    if len(words) < 2:   # chỉ 1 từ (username viết liền) -> đặt tên gọi tự nhiên, cố định theo username
        pool = NAMES_F if gender == "female" else NAMES_M
        nick = pool[int(hashlib.md5(username.encode()).hexdigest(), 16) % len(pool)]
    return Persona(
        username=username,
        display_name=display_name or username,
        gender=gender,
        nick=nick,
        mood=mood,
        tts_rate=tts_rate,
        charm=rng.choice(CHARMS),
        facts=f"nhóm em đi {rng.randint(2, 4)} người; giờ em muốn hẹn: {rng.choice(['7 giờ tối', '7 rưỡi tối', '8 giờ tối'])}",
        region=region,
        region_style=style,
        goal=goal,
        scenario_tag=tag,
        age=rng.randint(20, 34),
        backstory=(f"{rng.choice(JOBS)}, ở {rng.choice(DISTRICTS)}, hay đi chơi với {rng.choice(GROUPS)}; "
                   f"gần đây: {rng.choice(RECENT)}."),
    )
