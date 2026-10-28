import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.menu import check_budget, get_menu, validate_menu


class TestCostFormats(unittest.TestCase):
    def test_none(self):
        report = check_budget(None)
        self.assertTrue(report["has_unknown"])
        self.assertEqual(len(report["items"]), 10)

    def test_dict_day_to_pair(self):
        costs = {"Понедельник": {"A": 100, "B": 120}}
        report = check_budget(costs)
        monday = [i for i in report["items"] if i["day"] == "Понедельник"]
        self.assertEqual(monday[0]["cost"], 100)
        self.assertEqual(monday[1]["cost"], 120)

    def test_dict_day_to_scalar(self):
        costs = {"Понедельник": 90}
        report = check_budget(costs)
        monday = [i for i in report["items"] if i["day"] == "Понедельник"]
        self.assertEqual(monday[0]["cost"], 90)
        self.assertIsNone(monday[1]["cost"])

    def test_list_of_tuples_with_day(self):
        costs = [{"day": "Понедельник", "cost_a": 110, "cost_b": 130}]
        report = check_budget(costs)
        monday = [i for i in report["items"] if i["day"] == "Понедельник"]
        self.assertEqual(monday[0]["cost"], 110)
        self.assertEqual(monday[1]["cost"], 130)

    def test_parallel_list(self):
        costs = [50, 60]
        report = check_budget(costs)
        self.assertIsInstance(report, dict)
        self.assertEqual(len(report["items"]), 10)

    def test_tuple_input(self):
        costs = [("Понедельник", 100, 110)]
        report = check_budget(costs)
        monday = [i for i in report["items"] if i["day"] == "Понедельник"]
        self.assertEqual(monday[0]["cost"], 100)
        self.assertEqual(monday[1]["cost"], 110)


class TestMenuValidation(unittest.TestCase):
    def test_missing_vegetarian_rejected(self):
        menu = [dict(item) for item in get_menu()]
        menu[0]["dish_a_vegetarian"] = False
        menu[0]["dish_b_vegetarian"] = False
        ok, errors = validate_menu(menu)
        self.assertFalse(ok)
        self.assertTrue(any("vegetarian" in e for e in errors))

    def test_empty_complaint_rejected(self):
        menu = [dict(item) for item in get_menu()]
        menu[0]["complaint_cluster"] = "   "
        ok, errors = validate_menu(menu)
        self.assertFalse(ok)
        self.assertTrue(any("complaint_cluster" in e for e in errors))

    def test_non_bool_vegetarian_rejected(self):
        menu = [dict(item) for item in get_menu()]
        menu[0]["dish_a_vegetarian"] = 1
        menu[0]["dish_b_vegetarian"] = 0
        ok, errors = validate_menu(menu)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
