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

from domain.menu import day_for_date, get_active_menu, vegetarian_letters_for_day
from domain.preorder import kitchen_summary
from repositories.storage import get_orders, get_subscribers, save_order, subscribe_chat

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
        payload["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup,
                                                                                                ensure_ascii=False)
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


def _short(text, limit=28):
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_order_keyboard(meal_date, db_path=None):
    day_name = day_for_date(meal_date if not isinstance(meal_date, str) else date.fromisoformat(meal_date))
    menu = get_active_menu(db_path)
    item = next((m for m in menu if m["day"] == day_name), None) if day_name else None
    label_a = "Блюдо A"
    label_b = "Блюдо B"
    if item:
        label_a = f"A — {_short(item['dish_a'])}"
        label_b = f"B — {_short(item['dish_b'])}"
    return {
        "inline_keyboard": [
            [
                {"text": label_a, "callback_data": f"order:{meal_date if not hasattr(meal_date, 'isoformat') else meal_date.isoformat()}:A"},
                {"text": label_b, "callback_data": f"order:{meal_date if not hasattr(meal_date, 'isoformat') else meal_date.isoformat()}:B"},
            ]
        ]
    }


def menu_text_for_date(meal_date, db_path=None):
    day_name = day_for_date(meal_date)
    menu = get_active_menu(db_path)
    dstr = meal_date.isoformat() if hasattr(meal_date, "isoformat") else str(meal_date)
    lines = [f"🍽️ Меню на {dstr} ({day_name or 'день'}):"]
    if day_name:
        item = next((m for m in menu if m["day"] == day_name), None)
        if item:
            lines.append(f"  A — {item['dish_a']}")
            lines.append(f"  B — {item['dish_b']}")
            veg = []
            if item.get("dish_a_vegetarian"):
                veg.append("A")
            if item.get("dish_b_vegetarian"):
                veg.append("B")
            if veg:
                lines.append(f"  🌱 Вегетарианские: {', '.join(veg)}")
            lines.append("")
            lines.append("Нажмите кнопку ниже, чтобы выбрать блюдо 👇")
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
                    send_message(token, chat_id, "⚠️ Некорректный выбор.")
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
                    send_message(
                        token,
                        chat_id,
                        f"✅ Заказ сохранён!\nДата: {meal_date}\nБлюдо: {dish}\n\n"
                        "Можно изменить выбор до закрытия предзаказа.",
                    )
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
        if chat_id is not None:
            try:
                subscribe_chat(chat_id, db_path=db_path)
            except Exception:
                pass
        if token:
            send_message(
                token,
                chat_id,
                "👋 Привет! Я бот предзаказа «Умной столовой».\n\n"
                "Здесь можно выбрать обед на завтра за пару секунд.\n\n"
                "Команды:\n"
                "📋 /menu — меню на завтра\n"
                "🛒 /order — выбрать блюдо\n"
                "🧾 /myorder — мой заказ\n"
                "❓ /help — помощь",
            )
        return
    if text.startswith("/help"):
        if token:
            send_message(
                token,
                chat_id,
                "ℹ️ Как пользоваться:\n"
                "/menu — посмотреть меню на завтра\n"
                "/order — выбрать блюдо (кнопками)\n"
                "/myorder — проверить свой заказ\n\n"
                "Заказ можно изменить до закрытия опроса.\n"
                "Администраторам доступна команда /summary YYYY-MM-DD.",
            )
        return
    if text.startswith("/menu"):
        d = next_school_day()
        if token:
            send_message(token, chat_id, menu_text_for_date(d, db_path=db_path))
        return
    if text.startswith("/order"):
        d = next_school_day()
        if token:
            send_message(
                token,
                chat_id,
                f"🛒 Выберите блюдо на {d.isoformat()}:",
                reply_markup=build_order_keyboard(d, db_path=db_path),
            )
        return
    if text.startswith("/myorder"):
        d = next_school_day()
        orders = [o for o in get_orders(d.isoformat(), db_path=db_path) if o["student_code"] == f"TG-{user_id}"]
        if token:
            if orders:
                send_message(token, chat_id, f"✅ Ваш заказ на {d.isoformat()}: блюдо {orders[0]['dish']}.")
            else:
                send_message(token, chat_id, f"ℹ️ Заказ на {d.isoformat()} пока не оформлен. Используйте /order.")
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
        veg_letters = vegetarian_letters_for_day(day_name, menu=get_active_menu(db_path)) if day_name else []
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
            text_out += f"\nРаспределение A/B для {summary['unknown_distribution']} не ответивших неизвестно."
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


def _kitchen_summary_text(orders, expected_diners, veg_letters, meal_date):
    summary = kitchen_summary(orders, expected_diners, veg_letters)
    text_out = (
        f"Сводка для кухни на {meal_date.isoformat() if hasattr(meal_date, 'isoformat') else meal_date}:\n"
        f"Порций A: {summary['a_orders']}\n"
        f"Порций B: {summary['b_orders']}\n"
        f"Вегетарианских: {summary['vegetarian_orders']}\n"
        f"Не ответили: {summary['unanswered']}\n"
        f"Базовые порции: {summary['base_portions']}\n"
        f"Резерв {summary['buffer_percent']}%: {summary['buffer']}\n"
        f"Итого порций: {summary['total_portions']}"
    )
    if summary["unknown_distribution"] > 0:
        text_out += f"\nРаспределение A/B для {summary['unknown_distribution']} не ответивших неизвестно."
    return text_out


def broadcast_menu(token, meal_date=None, db_path=None):
    """Отправить меню на дату всем подписчикам бота. Возвращает число успешных отправок."""
    if meal_date is None:
        meal_date = next_school_day()
    if isinstance(meal_date, str):
        meal_date = date.fromisoformat(meal_date)
    chat_ids = get_subscribers(db_path)
    text = menu_text_for_date(meal_date, db_path=db_path)
    keyboard = build_order_keyboard(meal_date, db_path=db_path)
    sent = 0
    for cid in chat_ids:
        try:
            send_message(token, cid, text, reply_markup=keyboard)
            sent += 1
        except Exception:
            continue
    return sent


def send_kitchen_summary_to_admins(token, meal_date=None, db_path=None, expected_diners=None):
    """Отправить сводку для кухни администраторам. Возвращает число успешных отправок."""
    if meal_date is None:
        meal_date = date.today()
    if isinstance(meal_date, str):
        meal_date = date.fromisoformat(meal_date)
    if expected_diners is None:
        try:
            expected_diners = int(os.environ.get("CANTEEN_EXPECTED_DINERS", "500"))
        except ValueError:
            expected_diners = 500
    orders = get_orders(meal_date.isoformat(), db_path=db_path)
    day_name = day_for_date(meal_date)
    veg_letters = vegetarian_letters_for_day(day_name, menu=get_active_menu(db_path)) if day_name else []
    text_out = _kitchen_summary_text(orders, expected_diners, veg_letters, meal_date)
    sent = 0
    for admin_id in get_admin_ids():
        try:
            send_message(token, admin_id, text_out)
            sent += 1
        except Exception:
            continue
    return sent


def run_daily_job(token=None, db_path=None, today=None, broadcast_menu_date=None, summary_date=None):
    """Разовая утренняя процедура: рассылка меню и сводка для кухни.

    Возвращает словарь с результатами отправки.
    """
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if today is None:
        today = date.today()
    if broadcast_menu_date is None:
        broadcast_menu_date = next_school_day(today)
    if summary_date is None:
        # Сводка готовится на текущий день (заказы собраны ранее).
        summary_date = today
    menu_sent = broadcast_menu(token, meal_date=broadcast_menu_date, db_path=db_path)
    summary_sent = send_kitchen_summary_to_admins(token, meal_date=summary_date, db_path=db_path)
    return {"menu_sent": menu_sent, "summary_sent": summary_sent,
            "broadcast_date": broadcast_menu_date.isoformat() if hasattr(broadcast_menu_date, "isoformat") else str(broadcast_menu_date),
            "summary_date": summary_date.isoformat() if hasattr(summary_date, "isoformat") else str(summary_date)}


def run_scheduled(token=None, db_path=None, broadcast_hour=9, broadcast_minute=0,
                  poll_interval=30, run_once_time=None):
    """Цикл планировщика: выполняет run_daily_job раз в день в заданное время."""
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    last_run_date = None
    while True:
        now = datetime.now() if False else None
        from datetime import datetime as _dt

        now = _dt.now()
        if (now.hour, now.minute) == (broadcast_hour, broadcast_minute) and last_run_date != now.date():
            last_run_date = now.date()
            try:
                run_daily_job(token=token, db_path=db_path, today=now.date())
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning("Scheduled daily job failed: %s", exc)
        # Для тестов/ручного запуска: если указано run_once_time и оно совпало, выходим.
        if run_once_time is not None and (now.hour, now.minute) >= run_once_time:
            break
        time.sleep(poll_interval)
