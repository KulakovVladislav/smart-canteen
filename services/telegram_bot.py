# -*- coding: utf-8 -*-
"""Необязательный Telegram-бот «Умной столовой» (стандартная библиотека, без зависимостей).

Бот разделён на два независимых сценария:

* ученик — смотрит меню, выбирает блюдо A/B и управляет своим заказом;
* сотрудник кухни — смотрит сводку, вносит остатки и историю измерений.

Роль определяется переменной окружения ``TELEGRAM_ADMIN_IDS``.
"""

import html
import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from domain.menu import day_for_date, get_active_menu, vegetarian_letters_for_day
from domain.preorder import kitchen_summary
from repositories.storage import (
    delete_order,
    get_leftovers,
    get_orders,
    get_subscribers,
    mark_scheduled_job_completed,
    save_leftover,
    save_order,
    subscribe_chat,
    unsubscribe_chat,
    was_scheduled_job_completed,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger(__name__)

WELCOME_IMAGE_URL = os.environ.get("CANTEEN_BOT_IMAGE_URL", "").strip() or None

_ORDER_DISHES = ("A", "B")
_WEEKDAYS_RU = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
_WEEKDAYS_RU_ACCUSATIVE = (
    "понедельник",
    "вторник",
    "среду",
    "четверг",
    "пятницу",
    "субботу",
    "воскресенье",
)
_MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


# ---------------------------------------------------------------------------
# Дата и меню
# ---------------------------------------------------------------------------

def _coerce_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def format_date_human(value, accusative=False):
    """Человекочитаемая дата: «пятница, 30 октября» или «на пятницу, 30 октября»."""
    parsed = _coerce_date(value)
    if parsed is None:
        return str(value)
    suffix = "" if parsed.year == date.today().year else f" {parsed.year}"
    weekdays = _WEEKDAYS_RU_ACCUSATIVE if accusative else _WEEKDAYS_RU
    return f"{weekdays[parsed.weekday()]}, {parsed.day} {_MONTHS_RU[parsed.month - 1]}{suffix}"


def _iso_date(value):
    parsed = _coerce_date(value)
    return parsed.isoformat() if parsed else str(value)


def next_school_day(from_date=None):
    """Ближайший учебный день после указанной даты (пятница → понедельник)."""
    d = from_date or date.today()
    d = d + timedelta(days=1)
    while d.weekday() > 4:
        d = d + timedelta(days=1)
    return d


def _menu_item(meal_date, db_path=None):
    day_name = day_for_date(meal_date)
    if not day_name:
        return None
    return next((m for m in get_active_menu(db_path) if m["day"] == day_name), None)


def _dish_name(item, dish):
    if not item:
        return dish
    key = "dish_a" if dish == "A" else "dish_b"
    return str(item.get(key) or dish)


def _is_vegetarian(item, dish):
    if not item:
        return False
    key = "dish_a_vegetarian" if dish == "A" else "dish_b_vegetarian"
    return bool(item.get(key))


def menu_image_url(meal_date, db_path=None):
    """Optional image from configured menu data; text is the reliable fallback."""
    try:
        item = _menu_item(meal_date, db_path)
        if item and item.get("image_url"):
            return str(item["image_url"])
    except Exception:
        pass
    return None


def dish_image_url(dish_name):
    """Reserved for a future managed media store; never uses a third-party URL."""
    return None


# ---------------------------------------------------------------------------
# Настройки и Telegram API
# ---------------------------------------------------------------------------

def get_bot_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None


def get_admin_ids():
    raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    result = set()
    normalized = raw.replace(";", ",").replace(" ", ",").replace("\n", ",").replace("\t", ",").replace("\r", ",")
    for part in normalized.split(","):
        part = part.strip()
        if part:
            result.add(part)
    return result


def is_admin(user_id):
    if user_id is None:
        return False
    return str(user_id).strip() in get_admin_ids()


def get_expected_diners():
    try:
        value = int(str(os.environ.get("CANTEEN_EXPECTED_DINERS", "500")).strip())
    except (TypeError, ValueError):
        value = 500
    return max(0, value)


def _api_url(token, method):
    return f"https://api.telegram.org/bot{token}/{method}"


def _flatten(payload, prefix=""):
    """Преобразование вложенных словарей/списков в поля формы Telegram."""
    result = {}
    for key, value in payload.items():
        full = f"{prefix}{key}" if not prefix else f"{prefix}[{key}]"
        if isinstance(value, dict):
            result.update(_flatten(value, full))
        elif isinstance(value, (list, tuple)):
            result[full] = json.dumps(value, ensure_ascii=False)
        else:
            result[full] = value
    return result


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


def send_message(token, chat_id, text, reply_markup=None, parse_mode="HTML", timeout=30):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(
            reply_markup, ensure_ascii=False
        )
    return api_call(token, "sendMessage", payload, timeout=timeout)


def send_photo(token, chat_id, photo, caption=None, reply_markup=None, parse_mode="HTML", timeout=30):
    payload = {"chat_id": chat_id, "photo": photo}
    if caption is not None:
        payload["caption"] = caption
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup if isinstance(reply_markup, str) else json.dumps(
            reply_markup, ensure_ascii=False
        )
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


def get_me(token=None):
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return api_call(token, "getMe")


def _reply(token, chat_id, text, reply_markup=None, parse_mode="HTML"):
    """Отправить сообщение только при наличии токена и чата (удобно для тестов)."""
    if not token or chat_id is None:
        return None
    return send_message(token, chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)


def _reply_photo(token, chat_id, photo, caption=None, reply_markup=None):
    if not token or chat_id is None:
        return None
    return send_photo(token, chat_id, photo, caption=caption, reply_markup=reply_markup)


def _send_photo_or_text(token, chat_id, photo, caption, keyboard):
    """Отправить фото с подписью; без фото или при сбое — обычный текст."""
    if not photo:
        return _reply(token, chat_id, caption, reply_markup=keyboard)
    try:
        return _reply_photo(token, chat_id, photo, caption=caption, reply_markup=keyboard)
    except Exception as exc:
        logger.warning("Photo send failed, falling back to text: %s", exc)
        return _reply(token, chat_id, caption, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------

def _short(text, limit=24):
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _home_button():
    return {"text": "🏠 Главное меню", "callback_data": "nav:home"}


def _home_row():
    return [_home_button()]


def build_main_keyboard(is_admin_user=False):
    """Главное меню, в котором действия зависят от роли собеседника."""
    if is_admin_user:
        rows = [
            [
                {"text": "📊 Сводка на сегодня", "callback_data": "nav:summary"},
                {"text": "📝 Внести остатки", "callback_data": "nav:leftover"},
            ],
            [
                {"text": "📋 Меню", "callback_data": "nav:menu"},
                {"text": "📈 История остатков", "callback_data": "nav:leftovers"},
            ],
            [{"text": "❓ Помощь", "callback_data": "nav:help"}],
        ]
    else:
        rows = [
            [{"text": "🛒 Заказать обед", "callback_data": "nav:order"}],
            [
                {"text": "🧾 Мой заказ", "callback_data": "nav:myorder"},
                {"text": "📋 Меню", "callback_data": "nav:menu"},
            ],
            [{"text": "❓ Помощь", "callback_data": "nav:help"}],
        ]
    return {"inline_keyboard": rows}


def build_readonly_menu_keyboard(is_admin_user=False):
    rows = []
    if is_admin_user:
        rows.append([{"text": "📊 Сводка на сегодня", "callback_data": "nav:summary"}])
    rows.append(_home_row())
    return {"inline_keyboard": rows}


def build_order_keyboard(meal_date, db_path=None, current_dish=None):
    """Кнопки выбора блюда. Текущий выбор помечается галочкой."""
    iso = _iso_date(meal_date)
    item = _menu_item(meal_date, db_path)
    current = str(current_dish).upper() if current_dish else None

    def dish_button(dish):
        name = _dish_name(item, dish)
        mark = "✅" if current == dish else "🍽️"
        veg = " 🌱" if _is_vegetarian(item, dish) else ""
        return {
            "text": f"{mark} {dish} · {_short(name)}{veg}",
            "callback_data": f"order:{iso}:{dish}",
        }

    rows = [[dish_button("A"), dish_button("B")]]
    if current in _ORDER_DISHES:
        rows.append([{"text": "❌ Отменить заказ", "callback_data": f"cancel:{iso}"}])
    rows.append(_home_row())
    return {"inline_keyboard": rows}


def _order_actions_keyboard(iso):
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Изменить блюдо", "callback_data": "nav:order"},
                {"text": "❌ Отменить заказ", "callback_data": f"cancel:{iso}"},
            ],
            _home_row(),
        ]
    }


def _order_confirmation_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🧾 Мой заказ", "callback_data": "nav:myorder"},
                {"text": "📋 Меню", "callback_data": "nav:menu"},
            ],
            _home_row(),
        ]
    }


def _leftover_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "✖️ Отмена", "callback_data": "leftover:cancel"}],
            _home_row(),
        ]
    }


def _summary_actions_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📝 Внести остатки", "callback_data": "nav:leftover"},
                {"text": "📈 История остатков", "callback_data": "nav:leftovers"},
            ],
            _home_row(),
        ]
    }


# ---------------------------------------------------------------------------
# Заказы и меню
# ---------------------------------------------------------------------------

def _order_code(user_id):
    if user_id is None:
        return None
    return f"TG-{user_id}"


def _student_order(user_id, meal_date, db_path=None):
    code = _order_code(user_id)
    if not code:
        return None
    try:
        orders = get_orders(_iso_date(meal_date), db_path=db_path)
    except Exception as exc:
        logger.exception("Failed to load orders: %s", exc)
        return None
    return next((o for o in orders if o["student_code"] == code), None)


def _is_current_order_date(meal_date):
    parsed = _coerce_date(meal_date)
    return parsed is not None and parsed == next_school_day()


def menu_text_for_date(meal_date, db_path=None, is_admin_user=False, current_dish=None):
    """Текст меню на дату. Для ученика добавляет состояние его выбора."""
    parsed = _coerce_date(meal_date)
    day_name = day_for_date(parsed) if parsed else None
    menu = get_active_menu(db_path)
    current = str(current_dish).upper() if current_dish else None

    if not day_name:
        lines = ["🍽️ <b>Меню на учебную неделю</b>", ""]
        for item in menu:
            veg = []
            if item.get("dish_a_vegetarian"):
                veg.append("A")
            if item.get("dish_b_vegetarian"):
                veg.append("B")
            lines.append(f"<b>{html.escape(str(item['day']))}</b>")
            lines.append(f"A — {html.escape(str(item['dish_a']))}")
            lines.append(f"B — {html.escape(str(item['dish_b']))}")
            if veg:
                lines.append(f"🌱 Вегетарианские: {', '.join(veg)}")
            lines.append("")
        return "\n".join(lines).rstrip()

    lines = [f"🍽️ <b>Меню на {html.escape(format_date_human(parsed, accusative=True))}</b>"]
    item = next((m for m in menu if m["day"] == day_name), None)
    if item is None:
        lines.append("")
        lines.append("На этот день меню ещё не опубликовано.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"<b>Блюдо A</b> — {html.escape(str(item['dish_a']))}")
    lines.append(f"<b>Блюдо B</b> — {html.escape(str(item['dish_b']))}")
    veg = []
    if item.get("dish_a_vegetarian"):
        veg.append("A")
    if item.get("dish_b_vegetarian"):
        veg.append("B")
    if veg:
        lines.append(f"🌱 Вегетарианские: {', '.join(veg)}")

    if not is_admin_user:
        lines.append("")
        if current in _ORDER_DISHES:
            lines.append(
                f"✅ Ваш выбор: <b>{current}</b> — {html.escape(_dish_name(item, current))}"
            )
            lines.append("Можно выбрать другое блюдо кнопкой ниже.")
        else:
            lines.append("Выберите блюдо кнопкой ниже 👇")
    return "\n".join(lines)


def _main_menu_caption(is_admin_user, user_id=None, db_path=None):
    target = next_school_day()
    target_label = format_date_human(target, accusative=True)
    if is_admin_user:
        try:
            today_orders = get_orders(date.today().isoformat(), db_path=db_path)
            a_count = sum(1 for o in today_orders if str(o["dish"]).upper() == "A")
            b_count = sum(1 for o in today_orders if str(o["dish"]).upper() == "B")
            status = f"\n📊 Сегодня заказов: <b>{len(today_orders)}</b> (A — {a_count}, B — {b_count})."
        except Exception:
            status = ""
        return (
            "🏠 <b>Главное меню сотрудника</b>\n\n"
            f"📅 Меню на {html.escape(target_label)}."
            f"{status}\n\n"
            "Сводка, остатки и меню — кнопками ниже 👇"
        )

    order = _student_order(user_id, target, db_path=db_path)
    if order:
        dish = str(order["dish"]).upper()
        item = _menu_item(target, db_path)
        status = f"✅ Ваш заказ на {html.escape(target_label)}: <b>{dish}</b> — {html.escape(_dish_name(item, dish))}."
    else:
        status = f"🛒 Заказ на {html.escape(target_label)} ещё не оформлен."
    return (
        "🏠 <b>Главное меню</b>\n\n"
        f"{status}\n\n"
        "Выберите действие кнопкой ниже 👇"
    )


def _welcome_image(db_path=None):
    return WELCOME_IMAGE_URL or menu_image_url(next_school_day(), db_path=db_path)


def _send_main_menu(chat_id, token, db_path=None, user_id=None, welcome=False):
    admin = is_admin(user_id)
    caption = _main_menu_caption(admin, user_id=user_id, db_path=db_path)
    if welcome:
        intro = (
            "👋 <b>Привет!</b> Я бот «Умной столовой» для сотрудников кухни.\n\n"
            if admin
            else "👋 <b>Привет!</b> Я бот предзаказа «Умной столовой».\n\n"
        )
        caption = intro + caption
    keyboard = build_main_keyboard(admin)
    photo = _welcome_image(db_path) if welcome else menu_image_url(next_school_day(), db_path=db_path)
    _send_photo_or_text(token, chat_id, photo, caption, keyboard)


def _send_menu_view(chat_id, token, user_id, db_path=None):
    admin = is_admin(user_id)
    target = next_school_day()
    order = None if admin else _student_order(user_id, target, db_path=db_path)
    current = str(order["dish"]).upper() if order else None
    caption = menu_text_for_date(target, db_path=db_path, is_admin_user=admin, current_dish=current)
    if admin:
        caption += "\n\n👀 Режим сотрудника: только просмотр."
        keyboard = build_readonly_menu_keyboard(True)
    else:
        keyboard = build_order_keyboard(target, db_path=db_path, current_dish=current)
    _send_photo_or_text(token, chat_id, menu_image_url(target, db_path=db_path), caption, keyboard)


def _send_order_view(chat_id, token, user_id, db_path=None):
    target = next_school_day()
    item = _menu_item(target, db_path)
    order = _student_order(user_id, target, db_path=db_path)
    current = str(order["dish"]).upper() if order else None
    label = html.escape(format_date_human(target, accusative=True))

    if item is None:
        caption = f"😔 На {label} меню ещё не опубликовано.\nПопробуйте позже."
        keyboard = build_main_keyboard(False)
    elif current:
        dish_name = html.escape(_dish_name(item, current))
        veg = " 🌱 вегетарианское" if _is_vegetarian(item, current) else ""
        caption = (
            f"✅ <b>Ваш заказ на {label}</b>\n\n"
            f"<b>Блюдо {current}</b> — {dish_name}{veg}\n\n"
            "Выберите другое блюдо кнопкой ниже или отмените заказ."
        )
        keyboard = build_order_keyboard(target, db_path=db_path, current_dish=current)
    else:
        caption = (
            f"🛒 <b>Заказ на {label}</b>\n\n"
            "Выберите блюдо — это одно нажатие. Передумать можно до дня обеда."
        )
        keyboard = build_order_keyboard(target, db_path=db_path)
    _send_photo_or_text(token, chat_id, menu_image_url(target, db_path=db_path), caption, keyboard)


def _send_my_order_view(chat_id, token, user_id, db_path=None):
    target = next_school_day()
    order = _student_order(user_id, target, db_path=db_path)
    label = html.escape(format_date_human(target, accusative=True))
    date_label = html.escape(format_date_human(target))
    if not order:
        _reply(
            token,
            chat_id,
            f"ℹ️ <b>Заказ на {label} не оформлен.</b>\n\nВыберите блюдо — это займёт одно нажатие.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "🛒 Заказать обед", "callback_data": "nav:order"}],
                    _home_row(),
                ]
            },
        )
        return

    dish = str(order["dish"]).upper()
    item = _menu_item(target, db_path)
    dish_name = html.escape(_dish_name(item, dish))
    veg = " 🌱 вегетарианское" if _is_vegetarian(item, dish) else ""
    _reply(
        token,
        chat_id,
        (
            "✅ <b>Ваш заказ</b>\n\n"
            f"📅 {date_label}\n"
            f"🍽️ <b>Блюдо {dish}</b> — {dish_name}{veg}\n\n"
            "Можно изменить выбор или отменить заказ."
        ),
        reply_markup=_order_actions_keyboard(target.isoformat()),
    )


def _cancel_student_order(chat_id, token, user_id, meal_date, db_path=None):
    if user_id is None:
        _reply(token, chat_id, "⚠️ Не удалось определить пользователя. Нажмите /start.")
        return
    parsed = _coerce_date(meal_date)
    if parsed is None:
        _reply(token, chat_id, "⚠️ Неверный формат даты. Используйте YYYY-MM-DD.")
        return
    if not _is_current_order_date(parsed):
        target = next_school_day()
        _reply(
            token,
            chat_id,
            (
                "ℹ️ <b>Этот заказ уже неактуален.</b>\n\n"
                f"Сейчас можно заказать на {html.escape(format_date_human(target, accusative=True))}."
            ),
            reply_markup=build_order_keyboard(target, db_path=db_path),
        )
        return
    iso = parsed.isoformat()
    try:
        deleted = delete_order(_order_code(user_id), iso, db_path=db_path)
    except Exception as exc:
        logger.exception("Failed to cancel order: %s", exc)
        _reply(
            token,
            chat_id,
            "⚠️ Не удалось отменить заказ. Попробуйте позже.",
            reply_markup=build_main_keyboard(False),
        )
        return

    label = html.escape(format_date_human(parsed, accusative=True))
    if deleted:
        caption = (
            f"❌ <b>Заказ на {label} отменён.</b>\n\n"
            "Можно сразу выбрать другое блюдо:"
        )
        keyboard = build_order_keyboard(parsed, db_path=db_path)
    else:
        caption = f"ℹ️ Заказа на {label} не было."
        keyboard = build_main_keyboard(False)
    _reply(token, chat_id, caption, reply_markup=keyboard)


def _save_student_order(chat_id, token, user_id, meal_date, dish, db_path=None):
    if user_id is None:
        _reply(token, chat_id, "⚠️ Не удалось определить пользователя. Нажмите /start.")
        return
    dish = str(dish).upper()
    if dish not in _ORDER_DISHES:
        _reply(
            token,
            chat_id,
            "⚠️ <b>Некорректный выбор.</b> Выберите блюдо A или B кнопкой.",
            reply_markup=build_main_keyboard(False),
        )
        return

    parsed = _coerce_date(meal_date)
    if parsed is None:
        _reply(token, chat_id, "⚠️ Неверный формат даты. Используйте YYYY-MM-DD.")
        return
    if not _is_current_order_date(parsed):
        target = next_school_day()
        _reply(
            token,
            chat_id,
            (
                "ℹ️ <b>Это меню уже неактуально.</b>\n\n"
                f"Сейчас можно заказать на {html.escape(format_date_human(target, accusative=True))}."
            ),
            reply_markup=build_order_keyboard(target, db_path=db_path),
        )
        return

    item = _menu_item(parsed, db_path)
    if item is None:
        _reply(
            token,
            chat_id,
            "😔 Меню на этот день ещё не опубликовано. Попробуйте позже.",
            reply_markup=build_main_keyboard(False),
        )
        return

    existing = _student_order(user_id, parsed, db_path=db_path)
    if existing and str(existing["dish"]).upper() == dish:
        _reply(
            token,
            chat_id,
            f"✅ <b>Блюдо {dish}</b> уже выбрано на {html.escape(format_date_human(parsed, accusative=True))}.\n\n"
            "Можно выбрать другое блюдо или отменить заказ.",
            reply_markup=_order_actions_keyboard(parsed.isoformat()),
        )
        return

    try:
        save_order(_order_code(user_id), parsed.isoformat(), dish, db_path=db_path)
    except Exception as exc:
        logger.exception("Failed to save order: %s", exc)
        _reply(
            token,
            chat_id,
            "⚠️ Не удалось сохранить заказ. Попробуйте позже.",
            reply_markup=build_main_keyboard(False),
        )
        return

    name = _dish_name(item, dish)
    veg = " 🌱 вегетарианское" if _is_vegetarian(item, dish) else ""
    title = "🔄 <b>Выбор изменён</b>" if existing else "✅ <b>Заказ сохранён</b>"
    caption = (
        f"{title}\n\n"
        f"📅 {html.escape(format_date_human(parsed))}\n"
        f"🍽️ <b>Блюдо {dish}</b> — {html.escape(name)}{veg}\n\n"
        "Можно изменить выбор, пока не наступил день обеда."
    )
    photo = item.get("image_url") or dish_image_url(name)
    _send_photo_or_text(token, chat_id, photo, caption, _order_confirmation_keyboard())


# ---------------------------------------------------------------------------
# Сводка, остатки, помощь
# ---------------------------------------------------------------------------

def _summary_text(meal_date, db_path=None, expected_diners=None):
    parsed = _coerce_date(meal_date) or date.today()
    expected = get_expected_diners() if expected_diners is None else expected_diners
    try:
        orders = get_orders(parsed.isoformat(), db_path=db_path)
    except Exception as exc:
        logger.exception("Failed to load orders: %s", exc)
        return None
    day_name = day_for_date(parsed)
    try:
        veg_letters = vegetarian_letters_for_day(day_name, menu=get_active_menu(db_path)) if day_name else []
    except Exception:
        veg_letters = []
    text_out = _kitchen_summary_text(orders, expected, veg_letters, parsed)
    if day_name is None:
        text_out += "\nℹ️ В этот день столовая не работает."
    return text_out


def _kitchen_summary_text(orders, expected_diners, veg_letters, meal_date):
    summary = kitchen_summary(orders, expected_diners, veg_letters)
    parsed = _coerce_date(meal_date)
    label = html.escape(format_date_human(parsed)) if parsed else html.escape(str(meal_date))
    text_out = (
        f"📊 <b>Сводка для кухни</b>\n"
        f"📅 {label}\n\n"
        f"🥗 Заказов A: <b>{summary['a_orders']}</b>\n"
        f"🍕 Заказов B: <b>{summary['b_orders']}</b>\n"
        f"🌱 Вегетарианских: <b>{summary['vegetarian_orders']}</b>\n"
        f"📋 Всего заказов: <b>{summary['total_orders']}</b>\n"
        f"⏳ Не ответили: <b>{summary['unanswered']}</b> (из {summary['expected_diners']})\n"
        f"📦 Базовые порции: <b>{summary['base_portions']}</b>\n"
        f"🛡️ Резерв {summary['buffer_percent']}%: <b>{summary['buffer']}</b>\n"
        f"✅ Итого порций: <b>{summary['total_portions']}</b>"
    )
    if summary.get("estimated_distribution") and (summary.get("est_a", 0) or summary.get("est_b", 0)):
        text_out += f"\n🔮 Оценка для не ответивших: A +{summary['est_a']}, B +{summary['est_b']}"
    if summary["unknown_distribution"] > 0:
        text_out += f"\n⚠️ Распределение A/B для {summary['unknown_distribution']} не ответивших неизвестно."
    if summary["total_orders"] == 0:
        text_out += "\nℹ️ Заказов пока нет."
    return text_out


def _send_summary_view(chat_id, token, meal_date=None, db_path=None):
    parsed = _coerce_date(meal_date) or date.today()
    text_out = _summary_text(parsed, db_path=db_path)
    if text_out is None:
        _reply(
            token,
            chat_id,
            "⚠️ Не удалось загрузить заказы. Попробуйте позже.",
            reply_markup=build_main_keyboard(True),
        )
        return
    _reply(token, chat_id, text_out, reply_markup=_summary_actions_keyboard())


def _send_leftovers_view(chat_id, token, db_path=None):
    try:
        rows = get_leftovers(db_path=db_path, limit=5)
    except Exception as exc:
        logger.exception("Failed to load leftovers: %s", exc)
        _reply(
            token,
            chat_id,
            "⚠️ Не удалось загрузить историю остатков. Попробуйте позже.",
            reply_markup=build_main_keyboard(True),
        )
        return
    if not rows:
        text_out = (
            "📈 <b>История остатков</b>\n\n"
            "Записей пока нет. После обеда внесите остатки кнопкой «📝 Внести остатки»."
        )
    else:
        lines = ["📈 <b>Последние остатки</b>", ""]
        for row in rows:
            mass = row.get("waste_mass_kg")
            portions = row.get("leftover_portions")
            mass_text = f"{mass:g} кг" if isinstance(mass, (int, float)) else "—"
            portions_text = f"{portions} порц." if portions is not None else "—"
            lines.append(
                f"• <b>{html.escape(format_date_human(row.get('record_date')))}</b>: "
                f"{mass_text}, {portions_text}"
            )
            note = str(row.get("note") or "").strip()
            if note:
                lines.append(f"  <i>{html.escape(note)}</i>")
        text_out = "\n".join(lines)
    _reply(
        token,
        chat_id,
        text_out,
        reply_markup={
            "inline_keyboard": [
                [{"text": "📝 Внести остатки", "callback_data": "nav:leftover"}],
                _home_row(),
            ]
        },
    )


def _help_text(is_admin_user):
    if is_admin_user:
        return (
            "ℹ️ <b>Как пользоваться (сотрудник кухни)</b>\n\n"
            "📊 <b>Сводка на сегодня</b> — порции, вегетарианцы, резерв и итог\n"
            "📝 <b>Внести остатки</b> — отходы и оставшиеся порции\n"
            "📈 <b>История остатков</b> — последние пять измерений\n"
            "📋 <b>Меню</b> — состав блюд (только просмотр)\n\n"
            "Команды:\n"
            "<code>/summary</code> — сводка на сегодня\n"
            "<code>/summary 2026-11-02</code> — сводка на дату\n"
            "<code>/leftover 1.5 2 примечание</code> — сохранить остатки\n\n"
            "Предзаказ ученики оформляют в этом Telegram-боте."
        )
    return (
        "ℹ️ <b>Как оформить предзаказ</b>\n\n"
        "🛒 <b>Заказать обед</b> — выберите вариант A или B на ближайший учебный день\n"
        "🧾 <b>Мой заказ</b> — проверьте, измените или отмените выбор\n"
        "📋 <b>Меню</b> — посмотрите блюда на завтра\n\n"
        "Команды:\n"
        "<code>/order</code> — выбрать блюдо\n"
        "<code>/myorder</code> — посмотреть заказ\n"
        "<code>/cancel</code> — отменить заказ\n"
        "<code>/stop</code> — отключить утренние сообщения"
    )


# ---------------------------------------------------------------------------
# Ввод остатков
# ---------------------------------------------------------------------------

_LEFTOVER_PENDING = {}
_LEFTOVER_PENDING_LOCK = threading.Lock()


def _leftover_is_pending(user_id):
    if user_id is None:
        return False
    with _LEFTOVER_PENDING_LOCK:
        return user_id in _LEFTOVER_PENDING


def _set_leftover_pending(user_id, value=True):
    if user_id is None:
        return
    with _LEFTOVER_PENDING_LOCK:
        if value:
            _LEFTOVER_PENDING[user_id] = True
        else:
            _LEFTOVER_PENDING.pop(user_id, None)


def _parse_leftover(text):
    parts = str(text or "").split()
    if len(parts) < 2:
        raise ValueError("need mass and portions")
    try:
        waste = float(parts[0].replace(",", "."))
        portion_value = float(parts[1].replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError("numbers expected") from exc
    if not math.isfinite(waste) or not math.isfinite(portion_value):
        raise ValueError("numbers must be finite")
    if not portion_value.is_integer():
        raise ValueError("portions must be integer")
    waste = float(waste)
    portions = int(portion_value)
    if waste < 0 or portions < 0:
        raise ValueError("values must be non-negative")
    note = " ".join(parts[2:]).strip()
    return waste, portions, note


def _start_leftover(chat_id, token, user_id):
    _set_leftover_pending(user_id, True)
    _reply(
        token,
        chat_id,
        (
            "📝 <b>Внести остатки после обеда</b>\n\n"
            "Отправьте одной строкой:\n"
            "<code>1.5 2 примечание</code>\n\n"
            "• <b>1.5</b> — масса отходов в кг\n"
            "• <b>2</b> — сколько порций осталось\n"
            "• примечание необязательно\n\n"
            "Запись добавится в историю. Отмена — кнопкой ниже."
        ),
        reply_markup=_leftover_keyboard(),
    )


def _save_leftover_from_text(chat_id, token, user_id, text, db_path=None):
    try:
        waste, portions, note = _parse_leftover(text)
        save_leftover(date.today().isoformat(), waste, portions, note, db_path=db_path)
    except ValueError as exc:
        logger.warning("Invalid leftover input: %s", exc)
        _reply(
            token,
            chat_id,
            "⚠️ <b>Не получилось сохранить.</b>\n\n"
            "Нужны два неотрицательных числа: кг и целое число порций.\n"
            "Пример: <code>1.5 2 примечание</code>",
            reply_markup=_leftover_keyboard(),
        )
        return
    except Exception as exc:
        logger.exception("Failed to save leftovers: %s", exc)
        _reply(
            token,
            chat_id,
            "⚠️ Не удалось сохранить остатки. Попробуйте позже.",
            reply_markup=build_main_keyboard(True),
        )
        return

    _set_leftover_pending(user_id, False)
    caption = (
        "✅ <b>Остатки сохранены</b>\n\n"
        f"♻️ Отходы: <b>{waste:g} кг</b>\n"
        f"🍽️ Осталось порций: <b>{portions}</b>"
    )
    if note:
        caption += f"\n📝 {html.escape(note)}"
    _reply(token, chat_id, caption, reply_markup=build_main_keyboard(True))


# ---------------------------------------------------------------------------
# Обработка обновлений
# ---------------------------------------------------------------------------

def _deny_student_action(chat_id, token, user_id, message):
    _reply(token, chat_id, message, reply_markup=build_main_keyboard(False))


def _deny_staff_action(chat_id, token, user_id, message):
    _reply(token, chat_id, message, reply_markup=build_main_keyboard(True))


def _handle_nav(action, chat_id, token, user_id, db_path=None):
    admin = is_admin(user_id)
    if action in ("home", "start", "back", "cancel"):
        _send_main_menu(chat_id, token, db_path=db_path, user_id=user_id)
    elif action == "menu":
        _send_menu_view(chat_id, token, user_id, db_path=db_path)
    elif action == "order":
        if admin:
            _deny_staff_action(
                chat_id, token, user_id,
                "Предзаказ доступен ученикам в этом Telegram-боте. Здесь — быстрые действия кухни.",
            )
        else:
            _send_order_view(chat_id, token, user_id, db_path=db_path)
    elif action == "myorder":
        if admin:
            _deny_staff_action(
                chat_id, token, user_id,
                "Предзаказ доступен ученикам в этом Telegram-боте. Здесь — быстрые действия кухни.",
            )
        else:
            _send_my_order_view(chat_id, token, user_id, db_path=db_path)
    elif action == "help":
        _reply(
            token,
            chat_id,
            _help_text(admin),
            reply_markup=build_main_keyboard(admin),
        )
    elif action == "summary":
        if not admin:
            _deny_student_action(
                chat_id, token, user_id,
                "🔒 Сводка для кухни доступна только сотрудникам.",
            )
        else:
            _send_summary_view(chat_id, token, db_path=db_path)
    elif action == "leftover":
        if not admin:
            _deny_student_action(
                chat_id, token, user_id,
                "🔒 Остатки вносят только сотрудники кухни.",
            )
        else:
            _start_leftover(chat_id, token, user_id)
    elif action == "leftovers":
        if not admin:
            _deny_student_action(
                chat_id, token, user_id,
                "🔒 История остатков доступна только сотрудникам.",
            )
        else:
            _send_leftovers_view(chat_id, token, db_path=db_path)
    else:
        _reply(
            token,
            chat_id,
            "ℹ️ Эта кнопка устарела. Вот главное меню.",
            reply_markup=build_main_keyboard(admin),
        )


def _handle_callback(data, chat_id, token, user_id, db_path=None):
    # Любая кнопка завершает режим ввода остатков, кроме повторного входа в него.
    if _leftover_is_pending(user_id):
        _set_leftover_pending(user_id, False)
    parts = str(data or "").split(":")
    if len(parts) == 3 and parts[0] == "order":
        if is_admin(user_id):
            _deny_staff_action(
                chat_id, token, user_id,
                "Предзаказ доступен ученикам в этом Telegram-боте. Здесь — быстрые действия кухни.",
            )
            return
        _save_student_order(chat_id, token, user_id, parts[1], parts[2], db_path=db_path)
        return
    if len(parts) == 2 and parts[0] == "cancel":
        if is_admin(user_id):
            _deny_staff_action(
                chat_id, token, user_id,
                "Предзаказ доступен ученикам в этом Telegram-боте. Здесь — быстрые действия кухни.",
            )
            return
        _cancel_student_order(chat_id, token, user_id, parts[1], db_path=db_path)
        return
    if len(parts) == 2 and parts[0] == "leftover" and parts[1] == "cancel":
        if not is_admin(user_id):
            _deny_student_action(chat_id, token, user_id, "🔒 Это действие доступно только сотрудникам.")
            return
        _set_leftover_pending(user_id, False)
        _reply(
            token,
            chat_id,
            "✖️ Ввод остатков отменён.",
            reply_markup=build_main_keyboard(True),
        )
        return
    if parts[0] == "nav":
        _handle_nav(parts[1] if len(parts) > 1 else "", chat_id, token, user_id, db_path=db_path)
        return
    _reply(
        token,
        chat_id,
        "ℹ️ Эта кнопка устарела. Вот главное меню.",
        reply_markup=build_main_keyboard(is_admin(user_id)),
    )


def _handle_update(update, token=None, db_path=None):
    update = update or {}
    message = update.get("message") or {}
    callback = update.get("callback_query")

    if callback:
        chat_id = (callback.get("message") or {}).get("chat", {}).get("id")
        user_id = (callback.get("from") or {}).get("id")
        if token:
            try:
                answer_callback(token, callback.get("id"))
            except Exception:
                pass
        _handle_callback(callback.get("data", ""), chat_id, token, user_id, db_path=db_path)
        return

    chat_id = (message.get("chat") or {}).get("id")
    user_id = (message.get("from") or {}).get("id")
    text = (message.get("text") or "").strip()
    admin = is_admin(user_id)

    if not text:
        if token and chat_id is not None:
            _reply(
                token,
                chat_id,
                "Я понимаю текст и кнопки. Нажмите /help или выберите действие ниже 👇",
                reply_markup=build_main_keyboard(admin),
            )
        return

    # Ожидающий ввод остатков: следующее сообщение сотрудника сохраняется как запись.
    if admin and _leftover_is_pending(user_id) and not text.startswith("/"):
        _save_leftover_from_text(chat_id, token, user_id, text, db_path=db_path)
        return

    command, _, args = text.partition(" ")
    command = command.split("@", 1)[0].lower()
    had_pending = admin and _leftover_is_pending(user_id)
    if had_pending and command not in ("/leftover", "/cancel"):
        # Любая другая команда завершает режим ввода остатков.
        _set_leftover_pending(user_id, False)
        had_pending = False

    if command == "/start":
        if chat_id is not None:
            try:
                subscribe_chat(chat_id, db_path=db_path)
            except Exception as exc:
                logger.warning("Failed to subscribe chat: %s", exc)
        if token:
            _send_main_menu(chat_id, token, db_path=db_path, user_id=user_id, welcome=True)
        return

    if command == "/stop":
        if chat_id is not None:
            unsubscribe_chat(chat_id, db_path=db_path)
        if token:
            _reply(token, chat_id, "Рассылка отключена. Чтобы подписаться снова, отправьте /start.")
        return

    if command == "/help":
        if token:
            _reply(token, chat_id, _help_text(admin), reply_markup=build_main_keyboard(admin))
        return

    if command == "/menu":
        if token:
            _send_menu_view(chat_id, token, user_id, db_path=db_path)
        return

    if command == "/order":
        if admin:
            if token:
                _deny_staff_action(
                    chat_id, token, user_id,
                    "Предзаказ доступен ученикам в этом Telegram-боте. Здесь — быстрые действия кухни.",
                )
        elif token:
            _send_order_view(chat_id, token, user_id, db_path=db_path)
        return

    if command == "/myorder":
        if admin:
            if token:
                _deny_staff_action(
                    chat_id, token, user_id,
                    "Предзаказ доступен ученикам в этом Telegram-боте. Здесь — быстрые действия кухни.",
                )
        elif token:
            _send_my_order_view(chat_id, token, user_id, db_path=db_path)
        return

    if command == "/cancel":
        if admin:
            if token:
                caption = "✖️ Ввод остатков отменён." if had_pending else "ℹ️ Нет активного действия."
                _reply(token, chat_id, caption, reply_markup=build_main_keyboard(True))
            _set_leftover_pending(user_id, False)
        elif token:
            _cancel_student_order(chat_id, token, user_id, next_school_day(), db_path=db_path)
        return

    if command == "/summary":
        if not admin:
            if token:
                _deny_student_action(
                    chat_id, token, user_id,
                    "🔒 Сводка для кухни доступна только сотрудникам.",
                )
            return
        meal_date = date.today()
        if args.strip():
            parsed = _coerce_date(args.strip())
            if parsed is None:
                if token:
                    _reply(token, chat_id, "⚠️ Неверный формат даты. Используйте YYYY-MM-DD.")
                return
            meal_date = parsed
        if token:
            _send_summary_view(chat_id, token, meal_date=meal_date, db_path=db_path)
        return

    if command == "/leftover":
        if not admin:
            if token:
                _deny_student_action(
                    chat_id, token, user_id,
                    "🔒 Остатки вносят только сотрудники кухни.",
                )
            return
        if not args.strip():
            if token:
                _start_leftover(chat_id, token, user_id)
        elif token:
            _save_leftover_from_text(chat_id, token, user_id, args.strip(), db_path=db_path)
        return

    if text.startswith("/"):
        if token:
            _reply(
                token,
                chat_id,
                f"🤔 Неизвестная команда <code>{html.escape(command)}</code>. Напишите /help.",
                reply_markup=build_main_keyboard(admin),
            )
        return

    if token:
        _reply(
            token,
            chat_id,
            "Выберите действие кнопкой ниже или напишите /help 👇",
            reply_markup=build_main_keyboard(admin),
        )


def handle_update(update, token=None, db_path=None):
    """Обёртка с защитой от неожиданных ошибок и понятным ответом пользователю."""
    message = (update or {}).get("message") or {}
    callback = (update or {}).get("callback_query") or {}
    chat_id = (callback.get("message") or {}).get("chat", {}).get("id") if callback else None
    user_id = (callback.get("from") or {}).get("id") if callback else (message.get("from") or {}).get("id")
    if chat_id is None:
        chat_id = (message.get("chat") or {}).get("id")
    try:
        return _handle_update(update, token=token, db_path=db_path)
    except Exception as exc:
        logger.exception("Unhandled Telegram update error: %s", exc)
        if token and callback.get("id"):
            try:
                answer_callback(token, callback.get("id"), text="Ошибка")
            except Exception:
                pass
        if token and chat_id is not None:
            try:
                _reply(
                    token,
                    chat_id,
                    "⚠️ Произошла ошибка. Попробуйте позже.",
                    reply_markup=build_main_keyboard(is_admin(user_id)),
                )
            except Exception:
                pass
        return None


# ---------------------------------------------------------------------------
# Рассылки и планировщик
# ---------------------------------------------------------------------------

def broadcast_menu(token, meal_date=None, db_path=None):
    """Отправить меню на дату всем подписчикам бота. Возвращает число успешных отправок."""
    if meal_date is None:
        meal_date = next_school_day()
    parsed = _coerce_date(meal_date)
    if parsed is None:
        raise ValueError("meal_date must be a date")
    chat_ids = get_subscribers(db_path)
    sent = 0
    for cid in chat_ids:
        try:
            admin = is_admin(cid)
            order = None if admin else _student_order(cid, parsed, db_path=db_path)
            current = str(order["dish"]).upper() if order else None
            text = menu_text_for_date(
                parsed,
                db_path=db_path,
                is_admin_user=admin,
                current_dish=current,
            )
            if admin:
                text += "\n\n👀 Режим сотрудника: только просмотр."
                keyboard = build_readonly_menu_keyboard(True)
            else:
                keyboard = build_order_keyboard(parsed, db_path=db_path, current_dish=current)
            _send_photo_or_text(token, cid, menu_image_url(parsed, db_path=db_path), text, keyboard)
            sent += 1
        except Exception:
            logger.warning("Broadcast failed for chat %s", cid, exc_info=True)
    return sent


def send_kitchen_summary_to_admins(token, meal_date=None, db_path=None, expected_diners=None):
    """Отправить сводку для кухни администраторам. Возвращает число успешных отправок."""
    if meal_date is None:
        meal_date = date.today()
    parsed = _coerce_date(meal_date)
    if parsed is None:
        raise ValueError("meal_date must be a date")
    text_out = _summary_text(parsed, db_path=db_path, expected_diners=expected_diners)
    if text_out is None:
        return 0
    sent = 0
    for admin_id in get_admin_ids():
        try:
            _reply(token, admin_id, text_out, reply_markup=build_main_keyboard(True))
            sent += 1
        except Exception:
            logger.warning("Failed to send summary to admin %s", admin_id, exc_info=True)
    return sent


def run_daily_job(token=None, db_path=None, today=None, broadcast_menu_date=None, summary_date=None):
    """Разовая утренняя процедура: рассылка меню и сводка для кухни."""
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
    return {
        "menu_sent": menu_sent,
        "summary_sent": summary_sent,
        "broadcast_date": _iso_date(broadcast_menu_date),
        "summary_date": _iso_date(summary_date),
    }


def run_scheduled(token=None, db_path=None, broadcast_hour=9, broadcast_minute=0,
                  poll_interval=30, run_once_time=None):
    """Цикл планировщика: один успешный запуск на дату, даже после перезапуска."""
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    while True:
        now = datetime.now()
        target = now.replace(hour=broadcast_hour, minute=broadcast_minute, second=0, microsecond=0)
        run_date = now.date().isoformat()
        if now >= target and not was_scheduled_job_completed("daily_broadcast", run_date, db_path=db_path):
            try:
                run_daily_job(token=token, db_path=db_path, today=now.date())
                mark_scheduled_job_completed("daily_broadcast", run_date, db_path=db_path)
            except Exception as exc:
                logger.warning("Scheduled daily job failed: %s", exc)
        # Для тестов/ручного запуска: если указано run_once_time и оно совпало, выходим.
        if run_once_time is not None and (now.hour, now.minute) >= run_once_time:
            break
        time.sleep(poll_interval)


def build_commands(is_admin_user=False):
    """Команды для меню «/» в Telegram, разделённые по ролям."""
    if is_admin_user:
        return [
            {"command": "start", "description": "Главное меню"},
            {"command": "summary", "description": "Сводка для кухни"},
            {"command": "leftover", "description": "Внести остатки"},
            {"command": "menu", "description": "Меню на учебный день"},
            {"command": "help", "description": "Помощь"},
        ]
    return [
        {"command": "start", "description": "Главное меню"},
        {"command": "menu", "description": "Меню на ближайший день"},
        {"command": "order", "description": "Выбрать блюдо"},
        {"command": "myorder", "description": "Мой заказ"},
        {"command": "cancel", "description": "Отменить заказ"},
        {"command": "stop", "description": "Отключить рассылку"},
        {"command": "help", "description": "Помощь"},
    ]


def sync_commands(token=None):
    """Обновить меню команд: ученическое по умолчанию и кухонное для сотрудников."""
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    result = {"default": 0, "admins": 0}
    api_call(token, "setMyCommands", {"commands": build_commands(False)})
    result["default"] = 1
    for admin_id in get_admin_ids():
        try:
            api_call(
                token,
                "setMyCommands",
                {"commands": build_commands(True), "scope": {"type": "chat", "chat_id": admin_id}},
            )
            result["admins"] += 1
        except Exception:
            logger.warning("Failed to set commands for admin %s", admin_id, exc_info=True)
    return result


def bot_status(token=None):
    """Проверка подключения без отправки сообщений."""
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return {
        "bot": api_call(token, "getMe"),
        "admins": len(get_admin_ids()),
        "subscribers": len(get_subscribers()),
    }


def run_bot(token=None, db_path=None, poll_timeout=20):
    token = token or get_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    try:
        sync_commands(token)
    except Exception as exc:
        logger.warning("Failed to sync Telegram commands: %s", exc)
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
                    logger.warning("Failed to handle Telegram update: %s", exc)
        except Exception as exc:
            logger.warning("Telegram polling failed: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    run_bot()
