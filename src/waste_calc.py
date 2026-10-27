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


def compute_report():
    rows = load_waste()
    week_total = 0
    day_rows = []
    for day, pct in rows:
        loss = BUDGET_PER_DAY * pct / 100.0
        week_total += loss
        day_rows.append({"day": day, "pct": pct, "loss": loss})
    year_waste = week_total * WEEKS_PER_YEAR
    util_year = WASTE_KG_PER_DAY * WASTE_COST_PER_KG * SCHOOL_DAYS_PER_YEAR
    total = year_waste + util_year
    avg_pct = sum(p for _, p in rows) / len(rows) if rows else 0.0
    weekly_budget = BUDGET_PER_DAY * DAYS_PER_WEEK
    scenarios = []
    for target in (15, 10, 5):
        saving_week = (avg_pct - target) / 100.0 * weekly_budget
        saving_year = saving_week * WEEKS_PER_YEAR
        scenarios.append({"target": target, "saving_week": saving_week, "saving_year": saving_year})
    return {
        "rows": day_rows,
        "week_total": week_total,
        "year_waste": year_waste,
        "util_year": util_year,
        "total": total,
        "avg_pct": avg_pct,
        "scenarios": scenarios,
    }


def main():
    report = compute_report()
    print("Потери по дням (% от бюджета 70 000 сом):")
    for r in report["rows"]:
        print(f"  {r['day']}: {r['pct']:g}% -> {fmt(r['loss'])} сом")
    print(f"Неделя: {fmt(report['week_total'])} сом")
    print(f"Год (35 недель): {fmt(report['year_waste'])} сом")
    print(f"Утилизация за год: {fmt(report['util_year'])} сом")
    print(f"Итого прямые потери: {fmt(report['total'])} сом")
    print("\nСценарии снижения отходов:")
    for s in report["scenarios"]:
        print(f"  до {s['target']}%: экономия в неделю {fmt(s['saving_week'])} сом, за год {fmt(s['saving_year'])} сом")


if __name__ == "__main__":
    main()
