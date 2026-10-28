# -*- coding: utf-8 -*-
"""Структуры данных меню и валидаторы (только стандартная библиотека)."""

from __future__ import annotations

COST_CEILING = 140

MENU = [
    {
        "day": "Понедельник",
        "dish_a": "Каша без комков (малая порция) + котлета с пюре",
        "dish_b": "Овощные котлеты с пюре",
        "complaint_cluster": "В каше комки, порция большая",
        "cost_assumption_note": "не указано",
        "dish_a_vegetarian": False,
        "dish_b_vegetarian": True,
    },
    {
        "day": "Вторник",
        "dish_a": "Куриный суп + макароны с двойной нормой сыра",
        "dish_b": "Овощной суп + макароны с сыром",
        "complaint_cluster": "В макаронах мало сыра",
        "cost_assumption_note": "не указано",
        "dish_a_vegetarian": False,
        "dish_b_vegetarian": True,
    },
    {
        "day": "Среда",
        "dish_a": "Рыбные наггетсы без костей + рис с овощами",
        "dish_b": "Овощные биточки + рис с овощами",
        "complaint_cluster": "Рыба холодная, с костями, рис сухой",
        "cost_assumption_note": "не указано",
        "dish_a_vegetarian": False,
        "dish_b_vegetarian": True,
    },
    {
        "day": "Четверг",
        "dish_a": "Гороховый суп + гуляш с гречкой",
        "dish_b": "Гороховый суп на овощном бульоне + гречка с тушёными овощами",
        "complaint_cluster": "Вегетарианцам нечего есть",
        "cost_assumption_note": "не указано",
        "dish_a_vegetarian": False,
        "dish_b_vegetarian": True,
    },
    {
        "day": "Пятница",
        "dish_a": "Запеканка творожная",
        "dish_b": "Школьная пицца без мяса",
        "complaint_cluster": "Не успевают из-за очереди и короткой перемены",
        "cost_assumption_note": "не указано",
        "dish_a_vegetarian": True,
        "dish_b_vegetarian": True,
    },
]


def get_menu(db_path=None):
    if db_path is not None:
        return get_active_menu(db_path)
    return [dict(item) for item in MENU]


def get_active_menu(db_path=None):
    saved = None
    from src.storage import get_saved_menu

    saved = get_saved_menu(db_path)
    if saved:
        return [dict(item) for item in saved]
    return get_menu()


def _is_nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def validate_menu(menu=None):
    if menu is None:
        menu = MENU
    errors = []
    if not isinstance(menu, (list, tuple)):
        return False, ["menu must be a list"]
    if len(menu) != 5:
        errors.append(f"expected 5 days, got {len(menu)}")
    for i, item in enumerate(menu):
        if not isinstance(item, dict):
            errors.append(f"day {i}: item must be a dict")
            continue
        for key in ("day", "dish_a", "dish_b", "complaint_cluster"):
            if key not in item or not _is_nonempty(item.get(key)):
                errors.append(f"day {i}: missing or empty '{key}'")
        veg_a = bool(item.get("dish_a_vegetarian", False))
        veg_b = bool(item.get("dish_b_vegetarian", False))
        if not (veg_a or veg_b):
            errors.append(f"day {i}: at least one dish must be vegetarian")
    return (len(errors) == 0, errors)


def is_valid_menu(menu=None):
    ok, _ = validate_menu(menu)
    return ok


def _cost_pair(value):
    """Нормализовать значение стоимости в пару (стоимость A, стоимость B)."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        ca = value.get("A", value.get("a", value.get("cost_a", value.get("dish_a"))))
        cb = value.get("B", value.get("b", value.get("cost_b", value.get("dish_b"))))
        return ca, cb
    if isinstance(value, (tuple, list)):
        ca = value[0] if len(value) > 0 else None
        cb = value[1] if len(value) > 1 else None
        return ca, cb
    return value, None


def _extract_costs(costs, menu):
    """Вернуть список (день, стоимость A, стоимость B) для дней меню."""
    if costs is None:
        return [(item["day"], None, None) for item in menu]

    if isinstance(costs, dict):
        return [(item["day"], *_cost_pair(costs.get(item["day"]))) for item in menu]

    if isinstance(costs, (list, tuple)):
        days = {item["day"] for item in menu}
        if costs and isinstance(costs[0], dict) and "day" in costs[0]:
            by_day = {c["day"]: c for c in costs}
            return [(item["day"], *_cost_pair(by_day.get(item["day"]))) for item in menu]
        if costs and isinstance(costs[0], (list, tuple)) and len(costs[0]) >= 2 and isinstance(costs[0][0], str) and costs[0][0] in days:
            by_day = {}
            for c in costs:
                if isinstance(c, (list, tuple)) and len(c) >= 2 and isinstance(c[0], str):
                    by_day[c[0]] = c[1:]
            return [(item["day"], *_cost_pair(by_day.get(item["day"]))) for item in menu]
        result = []
        for idx, item in enumerate(menu):
            value = costs[idx] if idx < len(costs) else None
            ca, cb = _cost_pair(value)
            result.append((item["day"], ca, cb))
        return result

    return [(item["day"], None, None) for item in menu]


def _status(cost, limit):
    if cost is None or cost == "не указано":
        return "НЕДОСТАТОЧНО ДАННЫХ"
    try:
        value = float(cost)
    except (TypeError, ValueError):
        return "НЕДОСТАТОЧНО ДАННЫХ"
    if value > limit:
        return "ПРЕВЫШЕНИЕ ЛИМИТА"
    return "OK"


def check_budget(costs=None, limit=COST_CEILING, menu=None):
    if menu is None:
        menu = get_menu()
    rows = _extract_costs(costs, menu)
    items = []
    unknown = []
    over_limit = []
    for day, ca, cb in rows:
        for dish, cost in (("A", ca), ("B", cb)):
            st = _status(cost, limit)
            items.append({
                "day": day,
                "dish": dish,
                "cost": cost,
                "cost_display": cost if cost is not None and cost != "не указано" else "не указано",
                "status": st,
            })
            label = f"{day} / блюдо {dish}"
            if st == "НЕДОСТАТОЧНО ДАННЫХ":
                unknown.append(label)
            elif st == "ПРЕВЫШЕНИЕ ЛИМИТА":
                over_limit.append(label)

    has_unknown = len(unknown) > 0
    has_over = len(over_limit) > 0

    if has_over:
        overall_status = "ПРЕВЫШЕНИЕ ЛИМИТА"
    elif has_unknown:
        overall_status = "НЕДОСТАТОЧНО ДАННЫХ"
    else:
        overall_status = "OK"

    ok = (not has_over) and (not has_unknown)

    summary_lines = [
        f"Потолок себестоимости: {limit} сом/порция.",
        f"Не указано: {len(unknown)} позиций." if has_unknown else "Все стоимости указаны.",
        f"Превышение лимита: {len(over_limit)} позиций." if has_over else "Превышений лимита нет.",
        "Статус: " + overall_status,
    ]
    summary = "\n".join(summary_lines)

    return {
        "limit": limit,
        "items": items,
        "details": items,
        "unknown": unknown,
        "over_limit": over_limit,
        "has_unknown": has_unknown,
        "has_over_limit": has_over,
        "ok": ok,
        "status": overall_status,
        "summary": summary,
    }


DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]


def day_for_date(value):
    """Вернуть русское название дня недели для даты (Пн-Пт) или None для выходного."""
    if hasattr(value, "weekday"):
        wd = value.weekday()
    else:
        import datetime
        try:
            d = datetime.date.fromisoformat(str(value))
        except ValueError:
            return None
        wd = d.weekday()
    if 0 <= wd <= 4:
        return DAY_NAMES[wd]
    return None


def is_vegetarian_dish(day, dish, menu=None):
    if menu is None:
        menu = MENU
    for item in menu:
        if item["day"] == day:
            if dish == "A":
                return bool(item.get("dish_a_vegetarian", False))
            if dish == "B":
                return bool(item.get("dish_b_vegetarian", False))
    return False


def vegetarian_letters_for_day(day, menu=None):
    if menu is None:
        menu = MENU
    result = []
    for item in menu:
        if item["day"] == day:
            if item.get("dish_a_vegetarian"):
                result.append("A")
            if item.get("dish_b_vegetarian"):
                result.append("B")
    return result

_DEPRECATED_ALIASES = {
    "validate": validate_menu,
    "check": check_budget,
    "get": get_menu,
}


def __getattr__(name):
    if name in _DEPRECATED_ALIASES:
        import warnings

        warnings.warn(
            f"src.menu.{name} is deprecated; use the canonical name instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED_ALIASES[name]
    raise AttributeError(f"module 'src.menu' has no attribute {name!r}")
