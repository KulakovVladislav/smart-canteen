# -*- coding: utf-8 -*-
"""Подсчёт предзаказов и формирование сводки для кухни (только стандартная библиотека)."""

from __future__ import annotations

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


def _shares_from_choice(default_choice):
    if default_choice == "A":
        return (1.0, 0.0)
    if default_choice == "B":
        return (0.0, 1.0)
    if default_choice == "split":
        return (0.5, 0.5)
    return None


def count_preorders(
    choices=None,
    default_choice=None,
    buffer_percent=BUFFER_PERCENT,
    historical_shares=None,
    vegetarian_letters=None,
):
    """Count preorder choices and compute portions with a safety buffer.

    Unanswered students are included in the total portion count, but are not
    silently assigned to a dish unless historical shares are explicitly provided.
    """
    items = list(choices) if choices is not None else []

    answered_a = 0
    answered_b = 0
    unanswered = 0
    invalid = 0

    for raw in items:
        if isinstance(raw, dict):
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

    if historical_shares is None:
        historical_shares = _shares_from_choice(default_choice)

    est_a = 0
    est_b = 0
    estimated = False
    if historical_shares is not None and unanswered_total > 0:
        try:
            sa, sb = historical_shares
            sa = float(sa)
            sb = float(sb)
        except (TypeError, ValueError):
            sa, sb = 0.0, 0.0
        total_share = sa + sb
        if total_share > 0:
            sa /= total_share
            sb /= total_share
            est_a = int(round(unanswered_total * sa))
            est_b = unanswered_total - est_a
            estimated = True

    a_portions = answered_a + est_a
    b_portions = answered_b + est_b
    base_portions = answered_a + answered_b + unanswered_total

    if vegetarian_letters is None:
        veg_letters = {"B"}
    else:
        veg_letters = {str(x).upper() for x in vegetarian_letters}
    # Для count_preorders известны только буквы, поэтому число вегетарианских —
    # оценка на основе переданных (или стандартных) вегетарианских букв.
    vegetarian = answered_b if "B" in veg_letters else 0
    if "A" in veg_letters:
        vegetarian += answered_a

    buffer = math.ceil(base_portions * buffer_percent / 100.0) if base_portions else 0
    total = base_portions + buffer

    unknown_distribution = 0 if estimated else unanswered_total

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
        "historical_shares": historical_shares,
        "estimated_distribution": estimated,
        "est_a": est_a,
        "est_b": est_b,
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
        "unknown_distribution": unknown_distribution,
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


def kitchen_summary(orders, expected_diners, vegetarian_letters=None, buffer_percent=BUFFER_PERCENT, historical_shares=None, default_choice=None):
    orders = list(orders) if orders else []
    veg_letters = {str(x).upper() for x in (vegetarian_letters or [])}
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

    if historical_shares is None:
        historical_shares = _shares_from_choice(default_choice)
    est_a = est_b = 0
    estimated = False
    if historical_shares is not None and unanswered > 0:
        try:
            sa, sb = historical_shares
            sa, sb = float(sa), float(sb)
        except (TypeError, ValueError):
            sa, sb = 0.0, 0.0
        total_share = sa + sb
        if total_share > 0:
            sa /= total_share
            sb /= total_share
            est_a = int(round(unanswered * sa))
            est_b = unanswered - est_a
            estimated = True

    a_portions = a_orders + est_a
    b_portions = b_orders + est_b
    buffer = math.ceil(base_portions * buffer_percent / 100.0) if base_portions else 0
    total_portions = base_portions + buffer
    unknown_distribution = 0 if estimated else unanswered
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
        "a_portions": a_portions,
        "b_portions": b_portions,
        "est_a": est_a,
        "est_b": est_b,
        "estimated_distribution": estimated,
        "a_distribution_known": a_orders,
        "b_distribution_known": b_orders,
        "unknown_distribution": unknown_distribution,
    }
_DEPRECATED_ALIASES = {
    "counts": count_preorders,
    "parse": count_preorders,
    "parse_preorders": count_preorders,
    "summary": summarize,
}


def __getattr__(name):
    if name in _DEPRECATED_ALIASES:
        import warnings

        warnings.warn(
            f"src.preorder.{name} is deprecated; use the canonical name instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED_ALIASES[name]
    raise AttributeError(f"module 'src.preorder' has no attribute {name!r}")
