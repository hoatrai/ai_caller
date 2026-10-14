# ai_caller — user AI ngẫu nhiên gọi thoại cho adminroot

Cứ vài phút (mặc định 3–10 phút, ngẫu nhiên) có 1 tài khoản test **ngẫu nhiên** gọi thoại tới
`adminroot` trong app Kèo. adminroot bấm **Nghe** là nói chuyện được như với người thật:
bot nghe → hiểu → trả lời bằng giọng tiếng Việt, mỗi cuộc có "kịch bản" khác nhau
(rủ đi nhậu, báo lỗi app, xin slot kèo, hỏi quán, báo tới trễ...).

**Không sửa dòng code nào của Flutter / Phoenix / WordPress.** Bot dùng đúng giao thức app đang dùng:
`room:chat_X_Y` → `init_user` → `call_invite` (call_type=voice) → `call_accept` → WebRTC offer/answer.
Server Phoenix tự gửi FCM/CallKit làm máy adminroot đổ chuông như cuộc gọi thường.

```
 scheduler (main.py)  ──chọn user ngẫu nhiên──▶  session.py
     login WP JWT  → Phoenix call_invite → chờ adminroot nghe → WebRTC (aiortc)
     ┌──────────────────────── vòng hội thoại ────────────────────────┐
     │ mic adminroot → VAD → STT (Groq Whisper) → LLM (Groq/Gemini)   │
     │            ← track audio ← TTS (edge-tts, giọng vi-VN) ←───────┘
```

## AI miễn phí — dùng gì?
| Việc | Dịch vụ (free) | Ghi chú |
|---|---|---|
| LLM | **Groq** `openai/gpt-oss-120b` | key free tại console.groq.com. Dự phòng tự động: **Gemini** `gemini-2.0-flash` (aistudio.google.com) |
| STT | **Groq** `whisper-large-v3-turbo` | nếu không có key Groq → tự dùng route sẵn có `nhau/v1/stt/transcribe` (stt-service anh tự host) |
| TTS | **edge-tts** | giọng `vi-VN-HoaiMyNeural` (nữ) / `vi-VN-NamMinhNeural` (nam), không cần key |

Mỗi cuộc ~1 lần STT + 1 lần LLM mỗi lượt nói → nằm thoải mái trong hạn mức free khi gọi vài phút/lần.
Chỉ cần **1 key Groq** là chạy được đủ cả STT + LLM.

## Cài đặt (trên server test, cạnh thư mục `simulate-test`)
```bash
cd ai_caller
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # điền GROQ_API_KEY (và/hoặc GEMINI_API_KEY)
cp config.example.json config.json
```
Trong `config.json` chỉ cần chỉnh:
- `admin_user_id`: ID WordPress của adminroot (nếu để 0, bot sẽ thử tự tra qua `wp/v2/users?slug=adminroot`).
- `accounts_file`: mặc định đọc luôn danh sách `accounts` trong `../simulate-test/config.json` (tự loại adminroot).
  Có thể thêm `"gender": "female"|"male"` cho từng account để cố định giọng đọc (chắc chắn nhất; không có thì bot đoán theo tên, log in rõ lý do).
- **VieNeu-TTS tự host (tuỳ chọn, chạy CPU, không cần key):** `venv/bin/pip install vieneu`, rồi đặt `"tts": {"provider": "vieneu"}`
  (hoặc giữ `edge` và chỉ bật `"vieneu_first_turn": true` để lời chào đầu dùng VieNeu). Mặc định dùng chế độ `v3nano` (24 kHz, nhẹ nhất).
  Lần chạy đầu sẽ tải model từ Hugging Face; bot nạp sẵn model lúc khởi động (`warmup`) nên cuộc gọi đầu không phải chờ.
  Đường lùi: nếu VieNeu lỗi, quá `vieneu_timeout_seconds` (5s), hoặc chậm hơn `vieneu_slow_seconds` (3s) `vieneu_slow_limit` (2) câu liên tiếp
  thì bot nghỉ VieNeu `vieneu_cooldown_seconds` (120s) và tự dùng edge-tts. Mỗi user có một giọng cố định (theo username, đúng giới tính, ưu tiên cùng vùng miền);
  muốn tự chọn thì đặt `vieneu_voices_female` / `vieneu_voices_male` (danh sách tên giọng, xem trong log lúc khởi động). Tuỳ chọn thêm: `vieneu_steps` (8 = nhanh hơn, hơi thô),
  `vieneu_threads`, `vieneu_mode: "v3turbo"` + `vieneu_precision: "int8"`.
- Giọng đọc tự nhiên hơn: đặt `"tts": {"provider": "gemini"}` (dùng GEMINI_API_KEY, lỗi thì tự lùi về edge-tts; free tier có hạn mức nên nhớ theo dõi).
- `interval_min_seconds` / `interval_max_seconds`: khoảng cách giữa các cuộc gọi.
- `quiet_hours`: giờ không gọi (mặc định 00:00–07:00 giờ VN).

## Chạy
```bash
python main.py --config config.json --dry-run           # xem sẽ gọi ai, chưa gọi thật
python main.py --config config.json --once              # gọi thử 1 cuộc
python main.py --config config.json --once --user duonganh --scenario "báo lỗi app"
python main.py --config config.json                     # chạy vòng lặp
sudo cp nhau-ai-caller.service /etc/systemd/system/ && sudo systemctl enable --now nhau-ai-caller
```
Log: console + `ai_caller.log`. Cooldown từng user lưu ở `ai_caller_state.json` (mặc định 90 phút/user).

## Hành vi
- Chỉ gọi được **đúng `admin_user_id`** (có chốt chặn trong code) — bot không bao giờ gọi user khác.
- adminroot không nghe sau `ring_timeout_seconds` (35s) → bot huỷ cuộc gọi (server tự gửi FCM huỷ chuông).
- adminroot từ chối / cúp máy → bot dừng ngay.
- Chen ngang: adminroot nói đè lên thì bot im ngay (barge-in) rồi nghe tiếp.
- Im lặng quá lâu 2 lần (25s/lần) hoặc quá `max_call_seconds` (240s) → bot chào rồi cúp máy.
- LLM có thể tự kết thúc cuộc gọi khi "xong việc" (tag `[CUP_MAY]`, không bị đọc ra).
- `admit_ai_if_asked: true` → nếu adminroot hỏi thật "bạn có phải AI không" thì bot thừa nhận. Đặt `false` nếu muốn giữ vai tuyệt đối.

## Kiểm thử đã chạy
`python tests/test_e2e.py` — giả lập Phoenix + adminroot bằng aiortc, mock STT/LLM/TTS:
invite → accept → offer/answer → audio 2 chiều → bot nghe được giọng, adminroot nghe được giọng bot → bot cúp máy. ✅

**Chưa test được trên hệ thống thật** (cần mạng tới site/Phoenix/FCM/điện thoại): hãy chạy `--once` thử đầu tiên.

## Lưu ý khi chạy thật
1. Server chạy bot cần mở **UDP outbound** (WebRTC). Nếu điện thoại adminroot ở mạng 4G NAT đối xứng mà không kết nối được
   (log `WebRTC: failed`), thêm TURN server vào `ice_servers` (vd coturn tự host, hoặc free tier của Metered/Open Relay).
2. `edge-tts` dùng endpoint đọc văn bản của Microsoft Edge — miễn phí nhưng **không chính thức**, có thể đổi/chặn.
   Nếu hỏng, chỉ cần thay hàm `Brain.synth()` trong `brain.py` (vẫn trả về PCM s16 mono 48k) bằng Piper/gTTS/Google TTS.
3. Groq free có giới hạn request/phút; khi bị 429 bot tự thử lại rồi chuyển sang Gemini. Nếu cả hai lỗi, bot nói
   "mạng em chập chờn, gọi lại sau" rồi cúp máy thay vì im lặng.
4. Dùng cho **adminroot (người biết đây là bot)** trên site test. Đừng mở rộng cho bot gọi user thật mà không báo.

## Triển khai bằng git (Windows đẩy lên → server kéo về)
Repo: https://github.com/hoatrai/ai_caller — `.env` và `config.json` (chứa key/tài khoản) đã nằm trong `.gitignore`,
nên **không bao giờ bị đẩy lên git**; mỗi máy tự giữ file riêng của mình.

**Trên Windows** (`C:\Users\admin\ai_caller`), lần đầu:
```
cd C:\Users\admin\ai_caller
git init
git branch -M main
git remote add origin https://github.com/hoatrai/ai_caller.git
git add .
git commit -m "ai_caller: anh Hùng, nói tự nhiên hơn, nói tự nhiên hơn"
git push -u origin main
```
Các lần sau chỉ cần: `git add . && git commit -m "..." && git push`.

**Trên server**, lần đầu:
```bash
cd /root && git clone https://github.com/hoatrai/ai_caller.git && cd ai_caller
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env            # điền GROQ_API_KEY (và/hoặc GEMINI_API_KEY)
cp config.example.json config.json   # chỉnh admin_user_id
cp nhau-ai-caller.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now nhau-ai-caller
```
Các lần cập nhật sau: `cd /root/ai_caller && bash deploy.sh` (git pull + cài thư viện + restart bot).

