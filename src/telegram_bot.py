# -*- coding: utf-8 -*-
"""Необязательный Telegram-бот для предзаказов (HTTP через стандартную библиотеку, без зависимостей)."""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from src.menu import get_menu, day_for_date, get_active_menu
from src.preorder import kitchen_summary
from src.storage import get_orders, save_order

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None


def get_admin_ids():
    raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    result = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            result.add(part)
    return result


def is_admin(user_id):
    return str(user_id) in get_admin_ids()


def next_school_day(from_date=None):
    d = from_date or date.today()
    d = d + timedelta(days=1)
    while d.weekday() > 4:
        d = d + timedelta(days=1)
    return d


def _api_url(token, method):
    return f"https://api.telegram.org/bot{token}/{method}"


def api_call(token, method, payload=None, timeout=30):
    url = _api_url(token, method)
    if payload is None:
        payload = {}
    data = urllib.parse.urlencode(_flatten(payload)).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {exc.code}: {raw}") from exc
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API not ok: {parsed}")
    return parsed.get("result")


def _flatten(payload, prefix=""):
    # Преобразование вложенных словарей/списков в поля формы, которые принимает Telegram.
    result = {}
    for key, value in payload.items():
        full = f"{prefix}{key}" if not prefix else f"{prefix}[{key}]"
        if isinstance(value, dict):
            result.update(_flatten(value, full))
        elif isinstance(value, (list, tuple)):
            # Telegram поддерживает reply_markup как JSON-строку; обрабатываем отдельно.
            result[full] = json.dumps(value, ensure_ascii=False)
        else:
            result[full] = value
    return result


def send_message(token, chat_id, text, reply_markup=None, timeout=30):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup, ensure_ascii=False)
    return api_call(token, "sendMessage", payload, timeout=timeout)


def answer_callback(token, callback_query_id, text=None, timeout=30):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return api_call(token, "answerCallbackQuery", payload, timeout=timeout)


def get_updates(token, offset=None, timeout=20):
    payload = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    return api_call(token, "getUpdates", payload, timeout=timeout + 5)


def build_order_keyboard(meal_date):
    return {
        "inline_keyboard": [
            [
                {"text": "Блюдо A", "callback_data": f"order:{meal_date}:A"},
                {"text": "Блюдо B", "callback_data": f"order:{meal_date}:B"},
            ]
        ]
    }


def menu_text_for_date(meal_date, db_path=None):
    day_name = day_for_date(meal_date)
    menu = get_active_menu(db_path)
    lines = [f"Меню на {meal_date.isoformat()} ({day_name or 'день'}):"]
    if day_name:
        item = next((m for m in menu if m["day"] == day_name), None)
        if item:
            lines.append(f"A — {item['dish_a']}")
            lines.append(f"B — {item['dish_b']}")
            return "\n".join(lines)
    for m in menu:
        lines.append(f"{m['day']}: A — {m['dish_a']} | B — {m['dish_b']}")
    return "\n".join(lines)


def handle_update(update, token=None, db_path=None):
    # Выполняем побочные эффекты сразу, если передан токен.
    message = update.get("message") or {}
    callback = update.get("callback_query")
    chat_id = None
    user_id = None
    text = None

    if callback:
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        user_id = callback.get("from", {}).get("id")
        data = callback.get("data", "")
        if token:
            try:
                answer_callback(token, callback.get("id"))
            except Exception:
                pass
        parts = data.split(":")
        if len(parts) == 3 and parts[0] == "order":
            meal_date = parts[1]
            dish = parts[2].upper()
            if dish not in ("A", "B"):
                if token:
                    send_message(token, chat_id, "Некорректный выбор.")
                return
            try:
                meal_date = date.fromisoformat(meal_date).isoformat()
            except ValueError:
                if token:
                    send_message(token, chat_id, "Неверный формат даты. Используйте YYYY-MM-DD.")
                return
            try:
                student_code = f"TG-{user_id}"
                save_order(student_code, meal_date, dish, db_path=db_path)
                if token:
                    send_message(token, chat_id, f"Заказ сохранён: {meal_date}, блюдо {dish}. Можно изменить до закрытия предзаказа.")
            except Exception as exc:
                if token:
                    send_message(token, chat_id, f"Не удалось сохранить заказ: {exc}")
            return
        if token:
            send_message(token, chat_id, "Неизвестная команда.")
        return

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = (message.get("text") or "").strip()

    if not text:
        return
    if text.startswith("/start"):
        if token:
            send_message(
                token,
                chat_id,
                "Привет! Я бот предзаказа «Умной столовой».\n"
                "Команды:\n/menu — меню\n/order — оформить заказ\n/myorder — мой заказ\n/help — помощь",
            )
        return
    if text.startswith("/help"):
        if token:
            send_message(token, chat_id, "Используйте /menu, /order, /myorder. Администраторы: /summary YYYY-MM-DD")
        return
    if text.startswith("/menu"):
        d = next_school_day()
        if token:
            send_message(token, chat_id, menu_text_for_date(d, db_path=db_path))
        return
    if text.startswith("/order"):
        d = next_school_day()
        if token:
            send_message(token, chat_id, f"Выберите блюдо на {d.isoformat()}:", reply_markup=build_order_keyboard(d.isoformat()))
        return
    if text.startswith("/myorder"):
        d = next_school_day()
        orders = [o for o in get_orders(d.isoformat(), db_path=db_path) if o["student_code"] == f"TG-{user_id}"]
        if token:
            if orders:
                send_message(token, chat_id, f"Ваш заказ на {d.isoformat()}: блюдо {orders[0]['dish']}.")
            else:
                send_message(token, chat_id, f"Заказ на {d.isoformat()} пока не оформлен.")
        return
    if text.startswith("/summary"):
        if not is_admin(user_id):
            if token:
                send_message(token, chat_id, "Доступ к сводке только для администраторов.")
            return
        arg = text.split(maxsplit=1)
        if len(arg) > 1:
            try:
                from datetime import date as _date

                d = _date.fromisoformat(arg[1].strip())
            except ValueError:
                if token:
                    send_message(token, chat_id, "Неверный формат даты. Используйте YYYY-MM-DD.")
                return
        else:
            d = date.today()
        expected = 500
        try:
            expected = int(os.environ.get("CANTEEN_EXPECTED_DINERS", "500"))
        except ValueError:
            expected = 500
        orders = get_orders(d.isoformat(), db_path=db_path)
        day_name = day_for_date(d)
        veg_letters = []
        if day_name:
            from src.menu import vegetarian_letters_for_day, get_active_menu

            veg_letters = vegetarian_letters_for_day(day_name, menu=get_active_menu(db_path))
        summary = kitchen_summary(orders, expected, veg_letters)
        text_out = (
            f"Дата: {d.isoformat()}\n"
            f"Порций A: {summary['a_orders']}\n"
            f"Порций B: {summary['b_orders']}\n"
            f"Вегетарианских: {summary['vegetarian_orders']}\n"
            f"Не ответили: {summary['unanswered']}\n"
            f"Базовые порции: {summary['base_portions']}\n"
            f"Резерв {summary['buffer_percent']}%: {summary['buffer']}\n"
            f"Итого порций: {summary['total_portions']}"
        )
        if summary["unknown_distribution"] > 0:
            text_out += f"\nРаспределение A/B для {summary['unknown_distribution']} неответивших неизвестно."
        if token:
            send_message(token, chat_id, text_out)
        return
    if token:
        send_message(token, chat_id, "Неизвестная команда. /help")


def run_bot(token=None, db_path=None, poll_timeout=20):
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    offset = None
    while True:
        try:
            updates = get_updates(token, offset=offset, timeout=poll_timeout)
            for upd in updates or []:
                offset = upd.get("update_id", 0) + 1
                try:
                    handle_update(upd, token=token, db_path=db_path)
                except Exception as exc:
                    # Не прерываем цикл опроса при ошибке.
                    logging.getLogger(__name__).warning("Failed to handle Telegram update: %s", exc)
        except Exception as exc:
            logging.getLogger(__name__).warning("Telegram polling failed: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    run_bot()