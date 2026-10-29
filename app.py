# -*- coding: utf-8 -*-
"""Точка входа CLI для демонстрации «Умной столовой»."""

import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_dotenv():
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_dotenv()

from domain.menu import day_for_date, get_active_menu, check_budget, vegetarian_letters_for_day
from domain.preorder import format_summary, kitchen_summary
from domain.economics import print_report
from repositories.storage import get_dish_costs, get_orders, seed_presentation_data


def cmd_menu():
    for item in get_active_menu():
        print(f"{item['day']}: A — {item['dish_a']} | B — {item['dish_b']}")
        print(f"   жалоба: {item['complaint_cluster']}")


def _next_school_day(today=None):
    target = (today or date.today()) + timedelta(days=1)
    while target.weekday() > 4:
        target += timedelta(days=1)
    return target


def cmd_preorder(meal_date=None):
    target = meal_date or _next_school_day()
    orders = get_orders(target.isoformat())
    day_name = day_for_date(target)
    vegetarian = vegetarian_letters_for_day(day_name, menu=get_active_menu()) if day_name else []
    try:
        expected = max(0, int(os.environ.get("CANTEEN_EXPECTED_DINERS", "500")))
    except (TypeError, ValueError):
        expected = 500
    summary = kitchen_summary(orders, expected, vegetarian)
    summary["vegetarian"] = summary["vegetarian_orders"]
    summary["total"] = summary["total_portions"]
    print("Данные из локальной SQLite-базы.")
    print(format_summary(summary, date=target.isoformat()))


def cmd_budget_check():
    saved = get_dish_costs()
    menu = get_active_menu()
    cost_dict = {}
    for item in menu:
        cost_dict[item["day"]] = {
            "A": saved.get((item["day"], "A")),
            "B": saved.get((item["day"], "B")),
        }
    report = check_budget(cost_dict, menu=menu)
    print(report["summary"])
    for it in report["items"]:
        print(f"  {it['day']} / {it['dish']}: {it['cost_display']} сом — {it['status']}")


def cmd_all():
    print("=== МЕНЮ НА 5 ДНЕЙ ===")
    cmd_menu()
    print()
    print("=== ПРЕДЗАКАЗ (сводка для повара) ===")
    cmd_preorder()
    print()
    print("=== ПРОВЕРКА БЮДЖЕТА ===")
    cmd_budget_check()
    print()
    print("=== ЭКОНОМИКА (потери и сценарии) ===")
    print_report()


def cmd_demo():
    """Explicitly create local presentation data for the next school day."""
    target = _next_school_day()
    seeded = seed_presentation_data(target.isoformat())
    print(
        f"Демонстрационный набор создан на {seeded['meal_date']}: "
        f"{seeded['orders']} заказов, {seeded['costs']} стоимостей, {seeded['leftovers']} измерения остатков."
    )


def main(argv=None):
    if argv is None:
        argv = sys.argv
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd == "menu":
        cmd_menu()
    elif cmd == "preorder":
        cmd_preorder()
    elif cmd == "budget-check":
        cmd_budget_check()
    elif cmd == "all":
        cmd_all()
    elif cmd == "demo":
        cmd_demo()
    else:
        print("Usage: python app.py [menu|preorder|budget-check|all|demo]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
