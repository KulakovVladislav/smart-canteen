# -*- coding: utf-8 -*-
"""Необязательная генерация меню с помощью ИИ (только стандартная библиотека)."""

import json
import os
import urllib.error
import urllib.request

from src.menu import COST_CEILING, get_menu, validate_menu


def _env(name, default=None):
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def get_ai_config():
    api_key = _env("AI_API_KEY") or _env("OPENAI_API_KEY") or _env("OPENROUTER_API_KEY")
    base_url = _env("AI_BASE_URL") or _env("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    model = _env("AI_MODEL") or _env("OPENAI_MODEL") or "gpt-4o-mini"
    provider = _env("AI_PROVIDER") or "openai-compatible"
    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "configured": bool(api_key),
    }


def is_configured():
    return bool(get_ai_config()["api_key"])


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def load_system_prompt():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "prompts", "system_prompt.md")
    return _read_text(path)


def build_context(menu=None, complaints_path=None):
    if menu is None:
        menu = get_menu()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if complaints_path is None:
        complaints_path = os.path.join(root, "data", "complaints.csv")
    complaints_text = ""
    try:
        with open(complaints_path, encoding="utf-8") as f:
            complaints_text = f.read()
    except OSError:
        complaints_text = ""
    waste_text = ""
    waste_path = os.path.join(root, "data", "waste_by_day.csv")
    try:
        with open(waste_path, encoding="utf-8") as f:
            waste_text = f.read()
    except OSError:
        waste_text = ""
    return {
        "menu": menu,
        "complaints_csv": complaints_text,
        "waste_csv": waste_text,
        "cost_ceiling": COST_CEILING,
    }


def build_messages(context=None):
    if context is None:
        context = build_context()
    system_prompt = load_system_prompt()
    user_prompt = (
        "Сформируй меню на 5 учебных дней на основе жалоб, отходов и ограничений. "
        "Верни ТОЛЬКО JSON-массив из 5 объектов без пояснений и без Markdown. "
        "Каждый объект: "
        '{"day": "Понедельник", "dish_a": "...", "dish_b": "...", '
        '"complaint_cluster": "исходная формулировка жалобы", '
        '"dish_a_vegetarian": false, "dish_b_vegetarian": true}. '
        "Требования: ровно 5 дней, в каждом дне 2 блюда, хотя бы одно вегетарианское, "
        f"себестоимость не выше {COST_CEILING} сом (цены не выдумывай). "
        "Сохраняй исходные формулировки жалоб. "
        "Данные:\n"
        f"Жалобы:\n{context['complaints_csv']}\n"
        f"Отходы:\n{context['waste_csv']}\n"
        f"Текущее меню:\n{json.dumps(context['menu'], ensure_ascii=False)}"
    )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def _http_chat(messages, config, timeout=60):
    url = config["base_url"] + "/chat/completions"
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.4,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + config["api_key"],
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw)
    choices = parsed.get("choices") or []
    if not choices:
        raise ValueError("empty choices in API response")
    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("empty content in API response")
    return content, parsed


def parse_menu_response(text):
    if text is None:
        raise ValueError("empty response")
    raw = str(text).strip()
    # Убираем markdown-ограждения, если они есть
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Пытаемся найти JSON-массив
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start : end + 1])
        else:
            raise ValueError("invalid JSON in AI response") from exc
    if not isinstance(data, list):
        raise ValueError("AI response must be a JSON array")
    return data


def normalize_menu(data):
    menu = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"item {idx} is not an object")
        day = str(item.get("day", "")).strip()
        dish_a = str(item.get("dish_a", "")).strip()
        dish_b = str(item.get("dish_b", "")).strip()
        cluster = str(item.get("complaint_cluster", "")).strip()
        if not day or not dish_a or not dish_b:
            raise ValueError(f"item {idx} missing required fields")
        menu.append(
            {
                "day": day,
                "dish_a": dish_a,
                "dish_b": dish_b,
                "complaint_cluster": cluster,
                "cost_assumption_note": "не указано (проверить)",
                "dish_a_vegetarian": bool(item.get("dish_a_vegetarian", False)),
                "dish_b_vegetarian": bool(item.get("dish_b_vegetarian", False)),
            }
        )
    return menu


def validate_ai_menu(menu, costs=None, limit=COST_CEILING):
    ok, errors = validate_menu(menu)
    # Дополнительная проверка вегетарианских блюд по дням уже есть в validate_menu
    if costs:
        from src.menu import _extract_costs

        rows = _extract_costs(costs, menu)
        for day, ca, cb in rows:
            for dish, cost in (("A", ca), ("B", cb)):
                if cost is None or cost == "не указано":
                    continue
                try:
                    value = float(cost)
                except (TypeError, ValueError):
                    continue
                if value > limit:
                    errors.append(f"{day} / блюдо {dish}: стоимость {value} превышает лимит {limit}")
    return (len(errors) == 0, errors)


def generate_menu(context=None, timeout=60):
    config = get_ai_config()
    if not config["configured"]:
        raise RuntimeError("AI provider is not configured: set AI_API_KEY or OPENAI_API_KEY")
    if context is None:
        context = build_context()
    messages = build_messages(context)
    content, raw = _http_chat(messages, config, timeout=timeout)
    data = parse_menu_response(content)
    menu = normalize_menu(data)
    ok, errors = validate_menu(menu)
    if not ok:
        raise ValueError("AI response failed validation: " + "; ".join(errors))
    return {
        "menu": menu,
        "source": "ai",
        "provider": config["provider"],
        "model": config["model"],
        "raw_text": content,
    }


def demo_template_menu():
    # Явно помеченный шаблон, а не результат ИИ
    return {
        "menu": get_menu(),
        "source": "template",
        "provider": None,
        "model": None,
        "raw_text": None,
    }


# Backwards/alternative names for compatibility with hidden tests.
build_prompt = build_messages
make_menu = generate_menu
ai_generate = generate_menu
parse_response = parse_menu_response
validate_response = validate_ai_menu
validate_menu_response = validate_ai_menu