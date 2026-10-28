# -*- coding: utf-8 -*-
# Расчёт потерь от отходов столовой. Стандартная библиотека Python.
import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data", "waste_by_day.csv")

# Параметры школы. Значения по умолчанию соответствуют кейсу; могут быть
# переопределены через переменные окружения без изменения кода.
BUDGET_PER_DAY = int(os.environ.get("CANTEEN_DAILY_BUDGET", "70000"))
DAYS_PER_WEEK = int(os.environ.get("CANTEEN_DAYS_PER_WEEK", "5"))
WEEKS_PER_YEAR = int(os.environ.get("CANTEEN_WEEKS_PER_YEAR", "35"))
SCHOOL_DAYS_PER_YEAR = int(os.environ.get("CANTEEN_SCHOOL_DAYS_PER_YEAR", "175"))
WASTE_KG_PER_DAY = float(os.environ.get("CANTEEN_WASTE_KG_PER_DAY", "60"))
WASTE_COST_PER_KG = float(os.environ.get("CANTEEN_WASTE_COST_PER_KG", "15"))

REQUIRED_COLUMNS = {"day", "waste_percent"}


def load_waste():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"waste data file not found: {CSV_PATH}")
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError(
                "waste CSV must contain columns: " + ", ".join(sorted(REQUIRED_COLUMNS))
            )
        for line_no, r in enumerate(reader, start=2):
            day = (r.get("day") or "").strip()
            raw_pct = r.get("waste_percent")
            if not day:
                raise ValueError(f"waste CSV row {line_no}: day is required")
            try:
                pct = float(raw_pct)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"waste CSV row {line_no}: waste_percent must be a number"
                ) from exc
            if pct < 0:
                raise ValueError(f"waste CSV row {line_no}: waste_percent must be non-negative")
            rows.append((day, pct))
    if not rows:
        raise ValueError("waste CSV contains no data rows")
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
    util_day = WASTE_KG_PER_DAY * WASTE_COST_PER_KG
    util_year = util_day * SCHOOL_DAYS_PER_YEAR
    # Это разные статьи расходов. Их сумма показывается только как объединённая
    # оценка, потому что двойной учёт нельзя исключить без исходных данных.
    combined_losses = year_waste + util_year
    avg_pct = sum(p for _, p in rows) / len(rows) if rows else 0.0
    weekly_budget = BUDGET_PER_DAY * DAYS_PER_WEEK
    scenarios = []
    for target in (15, 10, 5):
        saving_week = max(0.0, (avg_pct - target) / 100.0 * weekly_budget)
        saving_year = saving_week * WEEKS_PER_YEAR
        scenarios.append({"target": target, "saving_week": saving_week, "saving_year": saving_year})
    return {
        "rows": day_rows,
        "week_total": week_total,
        "year_waste": year_waste,
        "util_day": util_day,
        "util_year": util_year,
        "utilization_year": util_year,
        "combined_losses": combined_losses,
        "total": combined_losses,
        "avg_pct": avg_pct,
        "scenarios": scenarios,
    }


def main():
    report = compute_report()
    print("Потери по дням (% от бюджета 70 000 сом):")
    for r in report["rows"]:
        print(f"  {r['day']}: {r['pct']:g}% -> {fmt(r['loss'])} сом")
    print(f"Неделя: {fmt(report['week_total'])} сом")
    print(f"Год (35 недель), продукты: {fmt(report['year_waste'])} сом")
    print(f"Утилизация в день: {fmt(report['util_day'])} сом")
    print(f"Утилизация за год: {fmt(report['util_year'])} сом")
    print(f"Сумма категорий (с риском двойного учёта): {fmt(report['combined_losses'])} сом")
    print("\nСценарии снижения отходов:")
    for s in report["scenarios"]:
        print(f"  до {s['target']}%: экономия в неделю {fmt(s['saving_week'])} сом, за год {fmt(s['saving_year'])} сом")


if __name__ == "__main__":
    main()
