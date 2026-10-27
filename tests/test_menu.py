import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.menu import get_menu, validate_menu, is_valid_menu, check_budget, COST_CEILING


class TestMenu(unittest.TestCase):
    def test_menu_has_five_days(self):
        self.assertEqual(len(get_menu()), 5)

    def test_menu_valid(self):
        ok, errors = validate_menu()
        self.assertTrue(ok, errors)

    def test_is_valid_menu(self):
        self.assertTrue(is_valid_menu())

    def test_two_dishes_per_day(self):
        for item in get_menu():
            self.assertTrue(item["dish_a"].strip())
            self.assertTrue(item["dish_b"].strip())

    def test_invalid_menu_wrong_count(self):
        ok, errors = validate_menu(get_menu()[:3])
        self.assertFalse(ok)
        self.assertTrue(errors)

    def test_invalid_menu_empty_dish(self):
        bad = get_menu()
        bad[0]["dish_a"] = ""
        ok, errors = validate_menu(bad)
        self.assertFalse(ok)

    def test_budget_unknown_by_default(self):
        report = check_budget()
        self.assertTrue(report["has_unknown"])
        self.assertFalse(report["has_over_limit"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "НЕДОСТАТОЧНО ДАННЫХ")

    def test_budget_over_limit(self):
        costs = {"Понедельник": {"A": 150, "B": 130}}
        report = check_budget(costs)
        self.assertTrue(report["has_over_limit"])
        self.assertFalse(report["ok"])

    def test_budget_ok(self):
        costs = {"Понедельник": {"A": 130, "B": 120}}
        report = check_budget(costs)
        self.assertFalse(report["has_over_limit"])

    def test_cost_ceiling(self):
        self.assertEqual(COST_CEILING, 140)

    def test_budget_tuple_input(self):
        costs = [("Понедельник", 100, 110)]
        # may not match day via list-of-tuples path; ensure no crash
        try:
            report = check_budget(costs)
            self.assertIsInstance(report, dict)
        except Exception as e:  # pragma: no cover
            self.fail(str(e))


if __name__ == "__main__":
    unittest.main()
