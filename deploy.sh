#!/usr/bin/env bash
# Chạy trên server: cập nhật code từ git rồi khởi động lại bot.   cd /root/ai_caller && bash deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
git pull --ff-only
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q -r requirements.txt
sudo systemctl restart nhau-ai-caller 2>/dev/null || systemctl restart nhau-ai-caller
sleep 2
systemctl --no-pager --lines=15 status nhau-ai-caller || true
