# -*- coding: utf-8 -*-
"""Необязательный Telegram-бот для предзаказов (HTTP через стандартную библиотеку, без зависимостей)."""

import html
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
from repositories.storage import get_orders, get_subscribers, save_leftover, save_order, subscribe_chat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WELCOME_IMAGE_URL = os.environ.get("CANTEEN_BOT_IMAGE_URL", "https://loremflickr.com/900/500/food,school?lock=2024")


def menu_image_url(meal_date, db_path=None):
    """Картинка для дня меню: из меню, если есть, иначе стабильная заглушка."""
    try:
        from domain.menu import day_for_date, get_active_menu

        day_name = day_for_date(meal_date)
        if day_name:
            item = next((m for m in get_active_menu(db_path) if m["day"] == day_name), None)
            if item and item.get("image_url"):
                return str(item["image_url"])
    except Exception:
        pass
    lock = 1
    if hasattr(meal_date, "weekday"):
        lock = int(meal_date.weekday()) + 1
    else:
        try:
            from datetime import date as _date

            lock = _date.fromisoformat(str(meal_date)).weekday() + 1
        except ValueError:
            lock = 1
    return f"https://loremflickr.com/900/500/food,school,meal?lock={lock}"


def dish_image_url(dish_name):
    """Стабильная картинка для конкретного блюда (включая новые блюда)."""
    name = str(dish_name or "").strip()
    lock = 1
    for ch in name:
        lock = (lock * 31 + ord(ch)) % 997
    if lock == 0:
        lock = 1
    return f"https://loremflickr.com/900/500/food,meal,dish?lock={lock}"

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


def send_message(token, chat_id, text, reply_markup=None, parse_mode="HTML", timeout=30):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup,
                                                                                                ensure_ascii=False)
    return api_call(token, "sendMessage", payload, timeout=timeout)


def send_photo(token, chat_id, photo, caption=None, reply_markup=None, parse_mode="HTML", timeout=30):
    payload = {"chat_id": chat_id, "photo": photo}
    if caption is not None:
        payload["caption"] = caption
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup,
                                                                                                ensure_ascii=False)
    return api_call(token, "sendPhoto", payload, timeout=timeout)


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
    label_a = "🥗 Блюдо A"
    label_b = "🍕 Блюдо B"
    if item:
        veg_a = " 🌱" if item.get("dish_a_vegetarian") else ""
        veg_b = " 🌱" if item.get("dish_b_vegetarian") else ""
        label_a = f"🥗 A — {_short(item['dish_a'])}{veg_a}"
        label_b = f"🍕 B — {_short(item['dish_b'])}{veg_b}"
    return {
        "inline_keyboard": [
            [
                {"text": label_a, "callback_data": f"order:{meal_date if not hasattr(meal_date, 'isoformat') else meal_date.isoformat()}:A"},
                {"text": label_b, "callback_data": f"order:{meal_date if not hasattr(meal_date, 'isoformat') else meal_date.isoformat()}:B"},
            ],
            [{"text": "🏠 Главное меню", "callback_data": "nav:home"}],
        ]
    }


def menu_text_for_date(meal_date, db_path=None):
    day_name = day_for_date(meal_date)
    menu = get_active_menu(db_path)
    dstr = meal_date.isoformat() if hasattr(meal_date, "isoformat") else str(meal_date)
    lines = [f"🍽️ <b>Меню на {html.escape(dstr)} ({html.escape(day_name or 'день')})</b>:"]
    if day_name:
        item = next((m for m in menu if m["day"] == day_name), None)
        if item:
            lines.append(f"  🥗 A — {html.escape(str(item['dish_a']))}")
            lines.append(f"  🍕 B — {html.escape(str(item['dish_b']))}")
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
        lines.append(f"{html.escape(str(m['day']))}: A — {html.escape(str(m['dish_a']))} | B — {html.escape(str(m['dish_b']))}")
    return "\n".join(lines)


def build_main_keyboard(is_admin_user=False):
    if is_admin_user:
        rows = [
            [
                {"text": "📊 Сводка на сегодня", "callback_data": "nav:summary"},
                {"text": "📝 Внести остатки", "callback_data": "nav:leftover"},
            ],
            [
                {"text": "📋 Меню на завтра", "callback_data": "nav:menu"},
                {"text": "🛒 Заказать обед", "callback_data": "nav:order"},
            ],
            [
                {"text": "🧾 Мой заказ", "callback_data": "nav:myorder"},
                {"text": "❓ Помощь", "callback_data": "nav:help"},
            ],
        ]
    else:
        rows = [
            [
                {"text": "📋 Меню на завтра", "callback_data": "nav:menu"},
                {"text": "🛒 Заказать обед", "callback_data": "nav:order"},
            ],
            [
                {"text": "🧾 Мой заказ", "callback_data": "nav:myorder"},
                {"text": "❓ Помощь", "callback_data": "nav:help"},
            ],
        ]
    rows.append([{"text": "🏠 Главное меню", "callback_data": "nav:home"}])
    return {"inline_keyboard": rows}


def _send_main_menu(chat_id, token, db_path=None, user_id=None):
    keyboard = build_main_keyboard(is_admin(user_id) if user_id is not None else False)
    caption = (
        "🏠 <b>Главное меню</b>\n\n"
        "Выберите действие кнопкой ниже 👇"
    )
    try:
        send_photo(token, chat_id, menu_image_url(d, db_path=db_path), caption=caption, reply_markup=keyboard)
    except Exception:
        send_message(token, chat_id, caption, reply_markup=keyboard)


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
                    send_message(token, chat_id, "⚠️ <b>Некорректный выбор.</b> Попробуйте снова.")
                return
            try:
                meal_date = date.fromisoformat(meal_date).isoformat()
            except ValueError:
                if token:
                    send_message(token, chat_id, "⚠️ Неверный формат даты. Используйте YYYY-MM-DD.")
                return
            try:
                student_code = f"TG-{user_id}"
                save_order(student_code, meal_date, dish, db_path=db_path)
                if token:
                    try:
                        day_name = day_for_date(date.fromisoformat(meal_date))
                        item = next((m for m in get_active_menu(db_path) if m["day"] == day_name), None)
                        selected_name = dish
                        if item:
                            selected_name = item["dish_a"] if dish == "A" else item["dish_b"]
                        photo = item.get("image_url") if item and item.get("image_url") else dish_image_url(selected_name)
                        send_photo(
                            token,
                            chat_id,
                            photo,
                            caption=(
                                f"✅ <b>Заказ сохранён!</b>\n"
                                f"📅 Дата: {html.escape(meal_date)}\n"
                                f"🍽️ Блюдо: <b>{html.escape(dish)} — {html.escape(str(selected_name))}</b>\n\n"
                                "Можно изменить выбор до закрытия предзаказа. 😊"
                            ),
                            reply_markup=build_main_keyboard(is_admin(user_id)),
                        )
                    except Exception:
                        send_message(
                            token,
                            chat_id,
                            f"✅ <b>Заказ сохранён!</b>\n"
                            f"📅 Дата: {html.escape(meal_date)}\n"
                            f"🍽️ Блюдо: <b>{html.escape(dish)}</b>\n\n"
                            "Можно изменить выбор до закрытия предзаказа. 😊",
                            reply_markup=build_main_keyboard(is_admin(user_id)),
                        )
            except Exception as exc:
                if token:
                    send_message(token, chat_id, f"Не удалось сохранить заказ: {exc}")
            return
        if data.startswith("nav:"):
            action = data.split(":", 1)[1]
            if token:
                if action in ("home", "start"):
                    _send_main_menu(chat_id, token, db_path=db_path, user_id=user_id)
                elif action == "menu":
                    d = next_school_day()
                    text_out = menu_text_for_date(d, db_path=db_path)
                    keyboard = build_order_keyboard(d, db_path=db_path)
                    try:
                        send_photo(token, chat_id, menu_image_url(d, db_path=db_path), caption=text_out, reply_markup=keyboard)
                    except Exception:
                        send_message(token, chat_id, text_out, reply_markup=keyboard)
                elif action == "order":
                    d = next_school_day()
                    caption = f"🛒 <b>Выберите блюдо на {html.escape(d.isoformat())}:</b>"
                    keyboard = build_order_keyboard(d, db_path=db_path)
                    try:
                        send_photo(token, chat_id, menu_image_url(d, db_path=db_path), caption=caption, reply_markup=keyboard)
                    except Exception:
                        send_message(token, chat_id, caption, reply_markup=keyboard)
                elif action == "myorder":
                    d = next_school_day()
                    orders = [o for o in get_orders(d.isoformat(), db_path=db_path) if o["student_code"] == f"TG-{user_id}"]
                    keyboard = build_main_keyboard(is_admin(user_id))
                    if orders:
                        send_message(token, chat_id, f"✅ <b>Ваш заказ на {html.escape(d.isoformat())}:</b> блюдо <b>{html.escape(str(orders[0]['dish']))}</b> 🎉", reply_markup=keyboard)
                    else:
                        send_message(token, chat_id, f"ℹ️ Заказ на {html.escape(d.isoformat())} пока не оформлен. Используйте /order. 🛒", reply_markup=keyboard)
                elif action == "help":
                    keyboard = build_main_keyboard(is_admin(user_id))
                    send_message(
                        token,
                        chat_id,
                        "ℹ️ <b>Как пользоваться:</b>\n"
                        "📋 /menu — посмотреть меню на завтра\n"
                        "🛒 /order — выбрать блюдо (кнопками)\n"
                        "🧾 /myorder — проверить свой заказ\n"
                        "Поварам: 📊 сводка и 📝 /leftover <кг> <порций>\n\n"
                        "Заказ можно изменить до закрытия опроса.\n"
                        "Администраторам: /summary YYYY-MM-DD. 🛠️",
                        reply_markup=keyboard,
                    )
                elif action == "leftover":
                    keyboard = build_main_keyboard(is_admin(user_id))
                    send_message(
                        token,
                        chat_id,
                        "📝 <b>Внести остатки после обеда</b>\n\n"
                        "Отправьте командой:\n"
                        "<code>/leftover 1.5 2 примечание</code>\n"
                        "где 1.5 кг отходов, 2 порции осталось.\n"
                        "Примечание необязательно.",
                        reply_markup=keyboard,
                    )
                elif action == "summary" and is_admin(user_id):
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
                        f"📊 <b>Сводка для кухни на {html.escape(d.isoformat())}</b>\n"
                        f"🥗 Порций A: <b>{summary['a_orders']}</b>\n"
                        f"🍕 Порций B: <b>{summary['b_orders']}</b>\n"
                        f"🌱 Вегетарианских: <b>{summary['vegetarian_orders']}</b>\n"
                        f"⏳ Не ответили: <b>{summary['unanswered']}</b>\n"
                        f"📦 Базовые порции: <b>{summary['base_portions']}</b>\n"
                        f"🛡️ Резерв {summary['buffer_percent']}%: <b>{summary['buffer']}</b>\n"
                        f"✅ Итого порций: <b>{summary['total_portions']}</b>"
                    )
                    if summary["unknown_distribution"] > 0:
                        text_out += f"\n⚠️ Распределение A/B для {summary['unknown_distribution']} не ответивших неизвестно."
                    keyboard = build_main_keyboard(True)
                    send_message(token, chat_id, text_out, reply_markup=keyboard)
            return
        if token:
            send_message(token, chat_id, "🤔 Неизвестная команда. Напишите /help.")
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
            try:
                send_photo(
                    token,
                    chat_id,
                    WELCOME_IMAGE_URL,
                    caption=(
                        "👋 <b>Привет! Я бот предзаказа «Умной столовой».</b>\n\n"
                        "Здесь можно выбрать обед на завтра за пару секунд 🚀\n\n"
                        "Выберите действие кнопкой ниже 👇"
                    ),
                    reply_markup=build_main_keyboard(is_admin(user_id)),
                )
            except Exception:
                send_message(
                    token,
                    chat_id,
                    "👋 <b>Привет! Я бот предзаказа «Умной столовой».</b>\n\n"
                    "Здесь можно выбрать обед на завтра за пару секунд 🚀\n\n"
                    "Выберите действие кнопкой ниже 👇",
                    reply_markup=build_main_keyboard(is_admin(user_id)),
                )
        return
    if text.startswith("/help"):
        if token:
            send_message(
                token,
                chat_id,
                "ℹ️ <b>Как пользоваться:</b>\n"
                "📋 /menu — посмотреть меню на завтра\n"
                "🛒 /order — выбрать блюдо (кнопками)\n"
                "🧾 /myorder — проверить свой заказ\n"
                "Поварам: 📊 сводка и 📝 /leftover <кг> <порций>\n\n"
                "Заказ можно изменить до закрытия опроса.\n"
                "Администраторам: /summary YYYY-MM-DD. 🛠️",
                reply_markup=build_main_keyboard(is_admin(user_id)),
            )
        return
    if text.startswith("/menu"):
        d = next_school_day()
        if token:
            text_out = menu_text_for_date(d, db_path=db_path)
            keyboard = build_order_keyboard(d, db_path=db_path)
            try:
                send_photo(token, chat_id, menu_image_url(d, db_path=db_path), caption=text_out, reply_markup=keyboard)
            except Exception:
                send_message(token, chat_id, text_out, reply_markup=keyboard)
        return
    if text.startswith("/order"):
        d = next_school_day()
        if token:
            caption = f"🛒 <b>Выберите блюдо на {html.escape(d.isoformat())}:</b>"
            keyboard = build_order_keyboard(d, db_path=db_path)
            try:
                send_photo(token, chat_id, menu_image_url(d, db_path=db_path), caption=caption, reply_markup=keyboard)
            except Exception:
                send_message(token, chat_id, caption, reply_markup=keyboard)
        return
    if text.startswith("/myorder"):
        d = next_school_day()
        orders = [o for o in get_orders(d.isoformat(), db_path=db_path) if o["student_code"] == f"TG-{user_id}"]
        if token:
            keyboard = build_main_keyboard(is_admin(user_id))
            if orders:
                send_message(token, chat_id, f"✅ <b>Ваш заказ на {html.escape(d.isoformat())}:</b> блюдо <b>{html.escape(str(orders[0]['dish']))}</b> 🎉", reply_markup=keyboard)
            else:
                send_message(token, chat_id, f"ℹ️ Заказ на {html.escape(d.isoformat())} пока не оформлен. Используйте /order. 🛒", reply_markup=keyboard)
        return
    if text.startswith("/leftover"):
        if not is_admin(user_id):
            if token:
                send_message(token, chat_id, "🔒 Внесение остатков доступно только поварам/администраторам.")
            return
        parts = text.split()
        if len(parts) < 3:
            if token:
                send_message(token, chat_id, "Использование: /leftover <кг> <порций> [примечание]")
            return
        try:
            waste = float(parts[1].replace(",", "."))
            portions = int(parts[2])
        except ValueError:
            if token:
                send_message(token, chat_id, "⚠️ Неверные числа. Пример: /leftover 1.5 2 примечание")
            return
        note = " ".join(parts[3:]) if len(parts) > 3 else ""
        try:
            save_leftover(date.today().isoformat(), waste, portions, note, db_path=db_path)
            if token:
                keyboard = build_main_keyboard(True)
                send_message(token, chat_id, f"✅ Остатки сохранены: {waste} кг, {portions} порций. {html.escape(note)}", reply_markup=keyboard)
        except Exception as exc:
            if token:
                send_message(token, chat_id, f"Не удалось сохранить остатки: {exc}")
        return
    if text.startswith("/summary"):
        if not is_admin(user_id):
            if token:
                send_message(token, chat_id, "🔒 Доступ к сводке только для администраторов.")
            return
        arg = text.split(maxsplit=1)
        if len(arg) > 1:
            try:
                from datetime import date as _date

                d = _date.fromisoformat(arg[1].strip())
            except ValueError:
                if token:
                    send_message(token, chat_id, "⚠️ Неверный формат даты. Используйте YYYY-MM-DD.")
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
            f"📊 <b>Сводка для кухни на {html.escape(d.isoformat())}</b>\n"
            f"🥗 Порций A: <b>{summary['a_orders']}</b>\n"
            f"🍕 Порций B: <b>{summary['b_orders']}</b>\n"
            f"🌱 Вегетарианских: <b>{summary['vegetarian_orders']}</b>\n"
            f"⏳ Не ответили: <b>{summary['unanswered']}</b>\n"
            f"📦 Базовые порции: <b>{summary['base_portions']}</b>\n"
            f"🛡️ Резерв {summary['buffer_percent']}%: <b>{summary['buffer']}</b>\n"
            f"✅ Итого порций: <b>{summary['total_portions']}</b>"
        )
        if summary["unknown_distribution"] > 0:
            text_out += f"\n⚠️ Распределение A/B для {summary['unknown_distribution']} не ответивших неизвестно."
        if token:
            send_message(token, chat_id, text_out)
        return
    if token:
        send_message(token, chat_id, "🤔 Неизвестная команда. Напишите /help.")


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
    dstr = meal_date.isoformat() if hasattr(meal_date, "isoformat") else str(meal_date)
    text_out = (
        f"📊 <b>Сводка для кухни на {html.escape(dstr)}</b>\n"
        f"🥗 Порций A: <b>{summary['a_orders']}</b>\n"
        f"🍕 Порций B: <b>{summary['b_orders']}</b>\n"
        f"🌱 Вегетарианских: <b>{summary['vegetarian_orders']}</b>\n"
        f"⏳ Не ответили: <b>{summary['unanswered']}</b>\n"
        f"📦 Базовые порции: <b>{summary['base_portions']}</b>\n"
        f"🛡️ Резерв {summary['buffer_percent']}%: <b>{summary['buffer']}</b>\n"
        f"✅ Итого порций: <b>{summary['total_portions']}</b>"
    )
    if summary["unknown_distribution"] > 0:
        text_out += f"\n⚠️ Распределение A/B для {summary['unknown_distribution']} не ответивших неизвестно."
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
            try:
                send_photo(token, cid, menu_image_url(meal_date, db_path=db_path), caption=text, reply_markup=keyboard)
            except Exception:
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
