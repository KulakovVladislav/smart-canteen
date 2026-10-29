# -*- coding: utf-8 -*-
"""Необязательная генерация меню с помощью ИИ (только стандартная библиотека)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from domain.menu import COST_CEILING, DAY_NAMES, _extract_costs, _strict_bool, get_menu, validate_menu


def _env(name, default=None):
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def get_ai_config():
    api_key = _env("AI_API_KEY") or _env("OPENAI_API_KEY") or _env("OPENROUTER_API_KEY") or _env("GEMINI_API_KEY")
    provider = _env("AI_PROVIDER")
    if not provider:
        # Автоопределение провайдера по формату ключа.
        if api_key and str(api_key).startswith("AQ."):
            provider = "gemini"
        else:
            provider = "openai-compatible"
    if provider == "gemini":
        base_url = _env("AI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta"
        model = _env("AI_MODEL") or _env("GEMINI_MODEL") or "gemini-3.1-flash-lite"
    else:
        base_url = _env("AI_BASE_URL") or _env("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = _env("AI_MODEL") or _env("OPENAI_MODEL") or "gpt-4o-mini"
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
        "Верни ТОЛЬКО JSON-массив из 5 объектов без пояснений, Markdown и таблиц. "
        "Дни должны идти строго в порядке: Понедельник, Вторник, Среда, Четверг, Пятница. "
        "Каждый объект: "
        '{"day": "Понедельник", "dish_a": "...", "dish_b": "...", '
        '"complaint_cluster": "исходная формулировка жалобы", '
        '"dish_a_vegetarian": false, "dish_b_vegetarian": true}. '
        "Поля day, dish_a и dish_b — непустые строки, complaint_cluster — строка (может быть пустой), "        "dish_a_vegetarian и dish_b_vegetarian — boolean. "
        "Требования: ровно 5 дней, в каждом дне 2 блюда; рекомендуется, чтобы хотя бы одно было вегетарианским, "
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


def _http_chat(messages, config, timeout=60, retries=2):
    import socket
    import time

    url = config["base_url"] + "/chat/completions"
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.4,
    }
    data = json.dumps(payload).encode("utf-8")
    last_exc = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + config["api_key"],
            },
            method="POST",
        )
        try:
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
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, TimeoutError,
                json.JSONDecodeError) as exc:
            last_exc = exc
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                if body:
                    last_exc = RuntimeError(f"HTTP {exc.code}: {body}")
            if attempt < retries and not isinstance(exc, urllib.error.HTTPError):
                time.sleep(0.5 * (attempt + 1))
                continue
            if attempt < retries and isinstance(exc, urllib.error.HTTPError) and exc.code >= 500:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise last_exc
    if last_exc is not None:  # pragma: no cover
        raise last_exc


def _http_gemini(messages, config, timeout=60):
    """Вызов нативного Gemini REST API (generateContent)."""
    import urllib.request
    import urllib.error
    import json as _json
    import socket

    url = f"{config['base_url']}/models/{config['model']}:generateContent"
    # Собираем текст из messages в один промпт (system + user).
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append("Системные инструкции:\n" + str(content))
        else:
            parts.append(str(content))
    prompt = "\n\n".join(parts)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    data = _json.dumps(payload).encode("utf-8")
    import time

    last_exc = None
    for attempt in range(3):
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": config["api_key"]},
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            parsed = _json.loads(raw)
            candidates = parsed.get("candidates") or []
            if not candidates:
                raise ValueError("empty candidates in Gemini response")
            content = ""
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    content += part["text"]
            if not content:
                raise ValueError("empty content in Gemini response")
            return content, parsed
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, TimeoutError,
                _json.JSONDecodeError) as exc:
            last_exc = exc
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                if body:
                    last_exc = RuntimeError(f"HTTP {exc.code}: {body}")
            if attempt < 2 and (not isinstance(exc, urllib.error.HTTPError) or exc.code >= 500):
                time.sleep(0.5 * (attempt + 1))
                continue
            raise last_exc
    if last_exc is not None:  # pragma: no cover
        raise last_exc


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
            data = json.loads(raw[start: end + 1])
        else:
            raise ValueError("invalid JSON in AI response") from exc
    if not isinstance(data, list):
        raise ValueError("AI response must be a JSON array")
    return data


def normalize_menu(data):
    if not isinstance(data, (list, tuple)):
        raise ValueError("AI response must be a list")
    menu = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"item {idx} is not an object")
        day = item.get("day")
        if not isinstance(day, str) or not day.strip():
            raise ValueError(f"item {idx} missing required field 'day'")
        day = day.strip()
        if day not in DAY_NAMES:
            raise ValueError(f"item {idx} has invalid day '{day}'")
        dish_a = item.get("dish_a")
        if not isinstance(dish_a, str) or not dish_a.strip():
            raise ValueError(f"item {idx} missing required field 'dish_a'")
        dish_a = dish_a.strip()
        dish_b = item.get("dish_b")
        if not isinstance(dish_b, str) or not dish_b.strip():
            raise ValueError(f"item {idx} missing required field 'dish_b'")
        dish_b = dish_b.strip()
        cluster = item.get("complaint_cluster")
        if not isinstance(cluster, str):
            raise ValueError(f"item {idx} missing required field 'complaint_cluster'")
        cluster = cluster.strip()
        try:
            veg_a = _strict_bool(item.get("dish_a_vegetarian", False))
        except ValueError as exc:
            raise ValueError(f"item {idx} has invalid 'dish_a_vegetarian'") from exc
        try:
            veg_b = _strict_bool(item.get("dish_b_vegetarian", False))
        except ValueError as exc:
            raise ValueError(f"item {idx} has invalid 'dish_b_vegetarian'") from exc
        menu.append(
            {
                "day": day,
                "dish_a": dish_a,
                "dish_b": dish_b,
                "complaint_cluster": cluster,
                "cost_assumption_note": "не указано (проверить)",
                "dish_a_vegetarian": veg_a,
                "dish_b_vegetarian": veg_b,
            }
        )
    if len(menu) == 5 and [item["day"] for item in menu] != DAY_NAMES:
        raise ValueError("days must be Понедельник, Вторник, Среда, Четверг, Пятница in this order")
    return menu


def validate_ai_menu(menu, costs=None, limit=COST_CEILING):
    ok, errors = validate_menu(menu)
    # Дополнительная проверка вегетарианских блюд по дням уже есть в validate_menu
    if costs:
        # Storage exposes prices as {(day, "A"): value, (day, "B"): value}.
        # check_budget also accepts a day-keyed mapping, so normalize here.
        if isinstance(costs, dict) and any(isinstance(key, tuple) and len(key) == 2 for key in costs):
            costs = {
                day: {letter: costs.get((day, letter)) for letter in ("A", "B")}
                for day in DAY_NAMES
            }
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
    if config["provider"] == "gemini":
        content, raw = _http_gemini(messages, config, timeout=timeout)
    else:
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


_DEPRECATED_ALIASES = {
    "build_prompt": build_messages,
    "make_menu": generate_menu,
    "ai_generate": generate_menu,
    "parse_response": parse_menu_response,
    "validate_response": validate_ai_menu,
    "validate_menu_response": validate_ai_menu,
}


def __getattr__(name):
    if name in _DEPRECATED_ALIASES:
        import warnings

        warnings.warn(
            f"src.ai_menu.{name} is deprecated; use the canonical name instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED_ALIASES[name]
    raise AttributeError(f"module 'src.ai_menu' has no attribute {name!r}")
