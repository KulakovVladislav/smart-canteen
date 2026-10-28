# -*- coding: utf-8 -*-
"""Точка входа CLI для демонстрации «Умной столовой»."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from domain.menu import get_menu, validate_menu, check_budget
from domain.preorder import SAMPLE_PREORDERS, count_preorders, format_summary
from domain.economics import print_report


def cmd_menu():
    for item in get_menu():
        print(f"{item['day']}: A — {item['dish_a']} | B — {item['dish_b']}")
        print(f"   жалоба: {item['complaint_cluster']}")


def cmd_preorder():
    counts = count_preorders(SAMPLE_PREORDERS)
    print(format_summary(counts))


def cmd_budget_check():
    report = check_budget()
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
    else:
        print("Usage: python app.py [menu|preorder|budget-check|all]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
