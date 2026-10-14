"""Nạp cấu hình cho ai_caller: config.json + biến môi trường (.env)."""
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv không bắt buộc
    load_dotenv = None

DEFAULTS = {
    "base_url": "https://spiritwebs.okinawanew.com",
    "websocket_url": "wss://socket.okinawanew.com/socket/websocket",
    "admin_username": "adminroot",
    "admin_user_id": 0,
    "accounts_file": "",
    "accounts": [],
    "interval_min_seconds": 180,
    "interval_max_seconds": 600,
    "same_user_cooldown_minutes": 90,
    "quiet_hours": {"enabled": True, "start": "00:00", "end": "07:00", "tz": "Asia/Ho_Chi_Minh"},
    "ring_timeout_seconds": 35,
    "max_call_seconds": 240,
    "idle_hangup_seconds": 25,
    "admit_ai_if_asked": True,
    "llm": {
        "providers": [
            {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b",
             "api_key_env": "GROQ_API_KEY", "max_tokens": 600, "extra": {"reasoning_effort": "low"}},
            {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-20b",
             "api_key_env": "GROQ_API_KEY", "max_tokens": 600, "extra": {"reasoning_effort": "low"}},
            {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
             "model": "gemini-2.0-flash", "api_key_env": "GEMINI_API_KEY"},
        ],
        "temperature": 0.9,
        "max_tokens": 120,
    },
    "stt": {"provider": "auto", "groq_model": "whisper-large-v3-turbo", "language": "vi"},
    "tts": {"voice_female": "vi-VN-HoaiMyNeural", "voice_male": "vi-VN-NamMinhNeural", "rate": "+6%"},
    "ice_servers": [{"urls": "stun:stun.l.google.com:19302"}],
}


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str) -> dict:
    p = Path(path).resolve()
    if load_dotenv:
        load_dotenv(p.parent / ".env")
    cfg = _merge(DEFAULTS, json.loads(p.read_text(encoding="utf-8")))

    # Danh sách tài khoản bot: ưu tiên "accounts" trong file này, nếu trống thì
    # đọc lại đúng danh sách accounts của simulate.py (khỏi nhập 2 lần).
    if not cfg["accounts"] and cfg.get("accounts_file"):
        af = (p.parent / cfg["accounts_file"]).resolve()
        if af.exists():
            cfg["accounts"] = json.loads(af.read_text(encoding="utf-8")).get("accounts", [])
    admin = cfg["admin_username"].lower()
    cfg["accounts"] = [a for a in cfg["accounts"]
                       if a.get("username") and str(a["username"]).lower() != admin]
    return cfg
