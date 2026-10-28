# -*- coding: utf-8 -*-
"""Точка входа Telegram-бота «Умной столовой»."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_dotenv():
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass

_load_dotenv()

from services.telegram_bot import (
    get_bot_token,
    run_bot,
    run_daily_job,
    run_scheduled,
)


def main(argv=None):
    if argv is None:
        argv = sys.argv
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd in ("run", "poll"):
        run_bot()
        return 0
    if cmd == "broadcast":
        result = run_daily_job()
        print(f"Рассылка выполнена: меню отправлено {result['menu_sent']}, "
              f"сводка отправлена {result['summary_sent']}.")
        return 0
    if cmd == "schedule":
        hour = int(os.environ.get("CANTEEN_BROADCAST_HOUR", "9"))
        minute = int(os.environ.get("CANTEEN_BROADCAST_MINUTE", "0"))
        run_scheduled(broadcast_hour=hour, broadcast_minute=minute)
        return 0
    print("Usage: python bot.py [run|poll|broadcast|schedule]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
