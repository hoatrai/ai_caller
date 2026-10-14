"""Tạo 'nhân vật' cho mỗi cuộc gọi: tên, giọng, tính cách, lý do gọi — ngẫu nhiên nhưng hợp lý."""
import hashlib
import random
from dataclasses import dataclass

# (mục tiêu cuộc gọi, câu gợi ý mở đầu — LLM tự diễn đạt lại, không đọc nguyên văn)
SCENARIOS = [
    ("Rủ anh Admin đi nhậu/ăn uống tối nay, hỏi anh có rảnh không và gợi ý khu vực.",
     "rủ đi nhậu tối nay"),
    ("Hỏi cách tìm kèo gần mình trong app: bật 'đang tìm kèo' rồi mà thấy ít người quá.",
     "hỏi cách tìm kèo gần nhà"),
    ("Báo một lỗi nhỏ gặp phải khi dùng app (vd: lúc gọi video bị giật, hoặc không thấy bạn bè trên bản đồ) và hỏi xem có sửa chưa.",
     "báo lỗi app"),
    ("Xin vào một kèo đang đầy chỗ, nhờ anh Admin giúp xem còn slot không.",
     "xin slot kèo"),
    ("Hỏi anh Admin gợi ý một quán nhậu/karaoke/bar ổn áp ở quận mình để rủ nhóm bạn đi.",
     "hỏi gợi ý quán"),
    ("Góp ý một tính năng mong muốn cho app (vd: chia tiền sau buổi nhậu, nhắc giờ hẹn), nói chuyện thân thiện.",
     "góp ý tính năng"),
    ("Gọi làm quen, hỏi thăm anh Admin dạo này thế nào, kể chuyện vừa đi kèo hôm qua vui ra sao.",
     "hỏi thăm kể chuyện kèo"),
    ("Báo là mình sẽ tới trễ một kèo mà anh Admin cũng có tham gia, xin lỗi và hỏi mọi người đã đến chưa.",
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
          "mới có một đứa bạn trong nhóm sắp cưới nên cả hội đang tính tụ tập", "vừa lên đời điện thoại mới nên đang dùng app thử đủ thứ"]

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

    @property
    def call_name(self) -> str:
        """Tên tự xưng trong lời nói (lấy từ cuối display_name, bỏ số/ký tự lạ)."""
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
    return Persona(
        username=username,
        display_name=display_name or username,
        gender=guess_gender(username, display_name or "", account.get("gender")),
        mood=rng.choice(MOODS),
        region=region,
        region_style=style,
        goal=goal,
        scenario_tag=tag,
        age=rng.randint(20, 34),
        backstory=(f"{rng.choice(JOBS)}, ở {rng.choice(DISTRICTS)}, hay đi chơi với {rng.choice(GROUPS)}; "
                   f"gần đây: {rng.choice(RECENT)}."),
    )
