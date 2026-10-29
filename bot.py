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
    bot_status,
    run_bot,
    run_daily_job,
    run_scheduled,
    sync_commands,
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
        try:
            hour = int(os.environ.get("CANTEEN_BROADCAST_HOUR", "9"))
            minute = int(os.environ.get("CANTEEN_BROADCAST_MINUTE", "0"))
        except (TypeError, ValueError):
            print("Неверное значение CANTEEN_BROADCAST_HOUR/MINUTE")
            return 2
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            print("CANTEEN_BROADCAST_HOUR должен быть 0-23, MINUTE 0-59")
            return 2
        run_scheduled(broadcast_hour=hour, broadcast_minute=minute)
        return 0
    if cmd == "check":
        try:
            status = bot_status()
        except Exception as exc:
            print(f"Проверка не удалась: {exc}")
            return 1
        bot = status["bot"] or {}
        username = bot.get("username")
        print(f"Бот: {bot.get('first_name', '—')}" + (f" (@{username})" if username else ""))
        print(f"Администраторы: {status['admins']}")
        print(f"Подписчики: {status['subscribers']}")
        return 0
    if cmd in ("commands", "sync"):
        try:
            result = sync_commands()
        except Exception as exc:
            print(f"Не удалось обновить команды: {exc}")
            return 1
        print(f"Команды обновлены: общее меню — {result['default']}, "
              f"персонально для сотрудников — {result['admins']}.")
        return 0
    print("Usage: python bot.py [run|poll|broadcast|schedule|check|commands]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
