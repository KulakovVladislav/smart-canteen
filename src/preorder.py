# -*- coding: utf-8 -*-
"""Preorder counting and kitchen summary generation (stdlib only)."""

import math

BUFFER_PERCENT = 5
VALID_CHOICES = {"A", "B"}


def _normalize(choice):
    if isinstance(choice, dict):
        for key in ("choice", "dish", "answer", "selection", "value", "option"):
            if key in choice:
                choice = choice[key]
                break
    if choice is None:
        return None
    text = str(choice).strip()
    if text == "":
        return None
    up = text.upper()
    if up in VALID_CHOICES:
        return up
    return None


def count_preorders(choices=None, default_choice="A", buffer_percent=BUFFER_PERCENT):
    """Count preorder choices and compute portions with a safety buffer.

    choices: iterable of "A"/"B" (case-insensitive), dicts with a choice key,
             or None/empty/invalid entries (treated as unanswered).
    """
    items = list(choices) if choices is not None else []

    answered_a = 0
    answered_b = 0
    unanswered = 0
    invalid = 0

    for raw in items:
        if isinstance(raw, dict):
            # track invalid separately only when a value present but bad
            had_value = any(k in raw for k in ("choice", "dish", "answer", "selection", "value", "option"))
            norm = _normalize(raw)
            if norm is None:
                if had_value:
                    invalid += 1
                else:
                    unanswered += 1
                continue
        else:
            text = "" if raw is None else str(raw).strip()
            if text == "":
                unanswered += 1
                continue
            norm = _normalize(raw)
            if norm is None:
                invalid += 1
                continue
        if norm == "A":
            answered_a += 1
        else:
            answered_b += 1

    unanswered_total = unanswered + invalid

    if default_choice == "B":
        default_a = 0
        default_b = unanswered_total
    elif default_choice == "split":
        default_a = unanswered_total // 2
        default_b = unanswered_total - default_a
    else:
        default_a = unanswered_total
        default_b = 0

    a_portions = answered_a + default_a
    b_portions = answered_b + default_b
    vegetarian = b_portions
    base_portions = a_portions + b_portions

    buffer = math.ceil(base_portions * buffer_percent / 100.0) if base_portions else 0
    total = base_portions + buffer

    return {
        "total_students": len(items),
        "a": answered_a,
        "b": answered_b,
        "a_count": answered_a,
        "b_count": answered_b,
        "count_a": answered_a,
        "count_b": answered_b,
        "answered_a": answered_a,
        "answered_b": answered_b,
        "unanswered": unanswered_total,
        "unanswered_count": unanswered_total,
        "invalid": invalid,
        "invalid_count": invalid,
        "default_choice": default_choice,
        "default_a": default_a,
        "default_b": default_b,
        "a_portions": a_portions,
        "b_portions": b_portions,
        "portions_a": a_portions,
        "portions_b": b_portions,
        "dish_a": a_portions,
        "dish_b": b_portions,
        "vegetarian": vegetarian,
        "vegetarian_count": vegetarian,
        "buffer_percent": buffer_percent,
        "buffer": buffer,
        "buffer_portions": buffer,
        "base_portions": base_portions,
        "total": total,
        "total_portions": total,
    }


def format_summary(counts, date="завтра"):
    lines = [
        f"Дата: {date}",
        f"Порций блюда A: {counts['a_portions']}",
        f"Порций блюда B: {counts['b_portions']}",
        f"Вегетарианских выборов: {counts['vegetarian']}",
        f"Не ответили: {counts['unanswered']}",
        f"Запас на отклонение ({counts['buffer_percent']}%): {counts['buffer']}",
        f"Итого порций к приготовлению: {counts['total']}",
    ]
    return "\n".join(lines)


def summarize(choices=None, date="завтра", **kwargs):
    counts = count_preorders(choices, **kwargs)
    return format_summary(counts, date=date)


def print_summary(choices=None, date="завтра", **kwargs):
    print(format_summary(count_preorders(choices, **kwargs), date=date))


# Hardcoded sample preorder list for the demo.
SAMPLE_PREORDERS = [
    "A", "A", "B", None, "A", "B", "B", "X", None, "A", "B", "A",
]


def kitchen_summary(orders, expected_diners, vegetarian_letters=None, buffer_percent=BUFFER_PERCENT):
    orders = list(orders) if orders else []
    veg_letters = set(vegetarian_letters or [])
    a_orders = sum(1 for o in orders if str(o.get("dish", "")).upper() == "A")
    b_orders = sum(1 for o in orders if str(o.get("dish", "")).upper() == "B")
    vegetarian_orders = sum(1 for o in orders if str(o.get("dish", "")).upper() in veg_letters)
    total_orders = len(orders)
    try:
        expected = int(expected_diners)
    except (TypeError, ValueError):
        expected = 0
    if expected < 0:
        expected = 0
    unanswered = max(0, expected - total_orders)
    base_portions = total_orders + unanswered
    buffer = math.ceil(base_portions * buffer_percent / 100.0) if base_portions else 0
    total_portions = base_portions + buffer
    return {
        "a_orders": a_orders,
        "b_orders": b_orders,
        "vegetarian_orders": vegetarian_orders,
        "total_orders": total_orders,
        "expected_diners": expected,
        "unanswered": unanswered,
        "base_portions": base_portions,
        "buffer_percent": buffer_percent,
        "buffer": buffer,
        "total_portions": total_portions,
        "a_distribution_known": a_orders,
        "b_distribution_known": b_orders,
        "unknown_distribution": unanswered,
    }
counts = count_preorders
parse = count_preorders
parse_preorders = count_preorders
summary = summarize
