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


def get_menu(db_path: str | None = None):
    if db_path is not None:
        return get_active_menu(db_path)
    return [dict(item) for item in MENU]


def get_active_menu(db_path: str | None = None):
    saved = None
    from repositories.storage import get_saved_menu

    saved = get_saved_menu(db_path)
    if saved:
        return [dict(item) for item in saved]
    return get_menu()


def _is_nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _strict_bool(value):
    """Строго разобрать булево значение без Python-истины строк."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise ValueError("expected a boolean value")


def validate_menu(menu=None) -> tuple[bool, list[str]]:
    if menu is None:
        menu = MENU
    errors = []
    if not isinstance(menu, (list, tuple)):
        return False, ["menu must be a list"]
    if len(menu) != 5:
        errors.append(f"expected 5 days, got {len(menu)}")
    days = []
    for i, item in enumerate(menu):
        if not isinstance(item, dict):
            errors.append(f"day {i}: item must be a dict")
            continue
        for key in ("day", "dish_a", "dish_b"):
            if key not in item or not _is_nonempty(item.get(key)):
                errors.append(f"day {i}: missing or empty '{key}'")
        if "complaint_cluster" not in item or not isinstance(item.get("complaint_cluster"), str):
            errors.append(f"day {i}: missing or invalid 'complaint_cluster'")
        if "day" in item and _is_nonempty(item.get("day")):
            days.append(str(item.get("day")).strip())
        veg_a = False
        veg_b = False
        for field, target in (("dish_a_vegetarian", "a"), ("dish_b_vegetarian", "b")):
            if field in item and item.get(field) is not None:
                try:
                    value = _strict_bool(item.get(field))
                except ValueError:
                    errors.append(f"day {i}: '{field}' must be a boolean")
                    value = False
                if target == "a":
                    veg_a = value
                else:
                    veg_b = value
            elif field in item and item.get(field) is None:
                errors.append(f"day {i}: '{field}' must be a boolean")
        # Наличие вегетарианского блюда не является обязательным по текущему контракту.
    if len(days) == 5 and days != DAY_NAMES:
        errors.append("days must be Понедельник, Вторник, Среда, Четверг, Пятница in this order")
    elif len(days) != 5 and len(menu) == 5:
        # Дублирующиеся или неизвестные дни уже отражены в списке days.
        pass
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
        if costs and isinstance(costs[0], (list, tuple)) and len(costs[0]) >= 2 and isinstance(costs[0][0], str) and \
                costs[0][0] in days:
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


def check_budget(costs=None, limit: int = COST_CEILING, menu=None) -> dict:
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
                "cost_display": "не указано" if cost is None or cost == "не указано" else (
                    str(int(cost)) if isinstance(cost, (int, float)) and not isinstance(cost, bool) and float(
                        cost).is_integer() else str(cost)
                ),
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


def day_for_date(value) -> str | None:
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
                return _strict_bool(item.get("dish_a_vegetarian", False))
            if dish == "B":
                return _strict_bool(item.get("dish_b_vegetarian", False))
    return False


def vegetarian_letters_for_day(day, menu=None):
    if menu is None:
        menu = MENU
    result = []
    for item in menu:
        if item["day"] == day:
            if _strict_bool(item.get("dish_a_vegetarian", False)):
                result.append("A")
            if _strict_bool(item.get("dish_b_vegetarian", False)):
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
            f"{__name__}.{name} is deprecated; use the canonical name instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED_ALIASES[name]
    raise AttributeError(f"module '{__name__}' has no attribute {name!r}")
