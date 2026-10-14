"""
ai_caller — cứ vài phút có 1 user (bot) NGẪU NHIÊN gọi thoại cho adminroot và
nói chuyện bằng giọng người thật. AI hoàn toàn miễn phí (Groq/Gemini free + edge-tts).

Chạy:
    python main.py --config config.json                # chạy vòng lặp
    python main.py --config config.json --once         # gọi thử 1 cuộc rồi thoát
    python main.py --config config.json --once --user duonganh --scenario "báo lỗi app"
    python main.py --config config.json --dry-run      # chỉ in ra sẽ gọi ai, không gọi
"""
import argparse
import asyncio
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from brain import Brain
from config import load_config
from persona import make_persona
from session import CallSession, login_bot, resolve_admin_id

log = logging.getLogger("ai_caller")


def in_quiet_hours(cfg) -> bool:
    q = cfg.get("quiet_hours") or {}
    if not q.get("enabled"):
        return False
    now = datetime.now(ZoneInfo(q.get("tz", "Asia/Ho_Chi_Minh"))).strftime("%H:%M")
    s, e = q["start"], q["end"]
    return (s <= now < e) if s <= e else (now >= s or now < e)


class State:
    """Nhớ lần gọi cuối của mỗi user (lưu file) để không gọi lặp 1 người liên tục."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.last = json.loads(path.read_text())
        except Exception:
            self.last = {}

    def mark(self, username):
        self.last[username] = time.time()
        try:
            self.path.write_text(json.dumps(self.last))
        except Exception:
            pass

    def available(self, accounts, cooldown_min):
        now = time.time()
        ok = [a for a in accounts if now - self.last.get(a["username"], 0) > cooldown_min * 60]
        return ok or accounts      # nếu ai cũng đang cooldown thì vẫn chọn tạm


async def one_call(cfg, brain, state, force_user=None, force_scenario=None, dry=False):
    accounts = cfg["accounts"]
    if not accounts:
        log.error("Không có tài khoản bot nào (accounts trống).")
        return
    if force_user:
        pool = [a for a in accounts if a["username"] == force_user]
        if not pool:
            log.error("Không thấy user %s trong accounts", force_user)
            return
    else:
        pool = state.available(accounts, cfg["same_user_cooldown_minutes"])
    random.shuffle(pool)

    bot = None
    for acc in pool[:5]:                      # thử tối đa 5 tài khoản nếu login lỗi
        try:
            bot = await login_bot(cfg, acc)
            break
        except Exception as e:
            log.warning("Login %s lỗi: %s", acc["username"], e)
    if not bot:
        return

    admin_id = await resolve_admin_id(cfg, bot["token"])
    persona = make_persona({"username": bot["username"], "gender": bot.get("gender")},
                           bot["display_name"], scenario_tag=force_scenario)
    log.info("Chọn %s (%s, %s) — %s", bot["username"], bot["display_name"], persona.gender, persona.scenario_tag)
    if dry:
        log.info("[dry-run] sẽ gọi adminroot (id=%s). Mục đích: %s", admin_id, persona.goal)
        return

    state.mark(bot["username"])
    sess = CallSession(cfg, brain, bot, persona, admin_id)
    try:
        res = await asyncio.wait_for(sess.run(), cfg["ring_timeout_seconds"] + cfg["max_call_seconds"] + 90)
        log.info("Kết thúc cuộc gọi: %s", res)
    except asyncio.TimeoutError:
        log.error("Cuộc gọi quá thời gian tối đa — đã ngắt.")
    except Exception:
        log.exception("Cuộc gọi lỗi")


async def amain(args):
    cfg = load_config(args.config)
    handlers = [logging.StreamHandler()]
    handlers.append(logging.FileHandler(Path(args.config).resolve().parent / "ai_caller.log", encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=handlers)
    logging.getLogger("aioice").setLevel(logging.WARNING)
    logging.getLogger("aiortc").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    state = State(Path(args.config).resolve().parent / "ai_caller_state.json")
    brain = Brain(cfg)
    try:
        if args.once or args.dry_run:
            await one_call(cfg, brain, state, args.user, args.scenario, dry=args.dry_run)
            return
        log.info("ai_caller chạy: gọi adminroot mỗi %d-%d giây", cfg["interval_min_seconds"],
                 cfg["interval_max_seconds"])
        wait = random.uniform(20, 60)
        while True:
            log.info("Cuộc gọi kế tiếp sau %.0f giây", wait)
            await asyncio.sleep(wait)
            if in_quiet_hours(cfg):
                log.info("Đang trong giờ yên tĩnh — bỏ qua lượt này.")
            else:
                await one_call(cfg, brain, state)
            wait = random.uniform(cfg["interval_min_seconds"], cfg["interval_max_seconds"])
    finally:
        await brain.aclose()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--user")
    ap.add_argument("--scenario")
    args = ap.parse_args()
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
