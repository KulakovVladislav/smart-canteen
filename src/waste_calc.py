# -*- coding: utf-8 -*-
# Расчёт потерь от отходов столовой. Стандартная библиотека Python.
import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data", "waste_by_day.csv")

# Параметры школы
BUDGET_PER_DAY = 70000          # дневной бюджет закупки, сом
DAYS_PER_WEEK = 5
WEEKS_PER_YEAR = 35
SCHOOL_DAYS_PER_YEAR = 175
WASTE_KG_PER_DAY = 60
WASTE_COST_PER_KG = 15


def load_waste():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((r["day"], float(r["waste_percent"])))
    return rows


def fmt(x):
    return f"{x:,.0f}".replace(",", " ")


def main():
    rows = load_waste()
    print("Потери по дням (% от бюджета 70 000 сом):")
    week_total = 0
    for day, pct in rows:
        loss = BUDGET_PER_DAY * pct / 100.0
        week_total += loss
        print(f"  {day}: {pct:g}% -> {fmt(loss)} сом")
    print(f"Неделя: {fmt(week_total)} сом")
    year_waste = week_total * WEEKS_PER_YEAR
    print(f"Год (35 недель): {fmt(year_waste)} сом")
    util_year = WASTE_KG_PER_DAY * WASTE_COST_PER_KG * SCHOOL_DAYS_PER_YEAR
    print(f"Утилизация за год: {fmt(util_year)} сом")
    total = year_waste + util_year
    print(f"Итого прямые потери: {fmt(total)} сом")

    avg_pct = sum(p for _, p in rows) / len(rows)
    weekly_budget = BUDGET_PER_DAY * DAYS_PER_WEEK
    print("\nСценарии снижения отходов:")
    for target in (15, 10, 5):
        saving_week = (avg_pct - target) / 100.0 * weekly_budget
        saving_year = saving_week * WEEKS_PER_YEAR
        print(f"  до {target}%: экономия в неделю {fmt(saving_week)} сом, за год {fmt(saving_year)} сом")


if __name__ == "__main__":
    main()
