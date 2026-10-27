# -*- coding: utf-8 -*-
"""Thin wrapper around waste_calc (no duplicate logic)."""

try:
    from . import waste_calc
except ImportError:  # pragma: no cover
    import waste_calc


def load_waste():
    return waste_calc.load_waste()


def fmt(x):
    return waste_calc.fmt(x)


BUDGET_PER_DAY = waste_calc.BUDGET_PER_DAY
DAYS_PER_WEEK = waste_calc.DAYS_PER_WEEK
WEEKS_PER_YEAR = waste_calc.WEEKS_PER_YEAR
SCHOOL_DAYS_PER_YEAR = waste_calc.SCHOOL_DAYS_PER_YEAR
WASTE_KG_PER_DAY = waste_calc.WASTE_KG_PER_DAY
WASTE_COST_PER_KG = waste_calc.WASTE_COST_PER_KG


def print_report():
    waste_calc.main()


def run():
    print_report()


def waste_report():
    return waste_calc.compute_report()


def main():
    print_report()


if __name__ == "__main__":
    main()
