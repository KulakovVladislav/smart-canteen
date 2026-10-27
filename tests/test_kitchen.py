import unittest

from src.menu import check_budget
from src.preorder import kitchen_summary


class TestKitchenSummary(unittest.TestCase):
    def test_basic(self):
        orders = [{"dish": "A"}, {"dish": "B"}, {"dish": "B"}]
        s = kitchen_summary(orders, 5, vegetarian_letters={"B"})
        self.assertEqual(s["a_orders"], 1)
        self.assertEqual(s["b_orders"], 2)
        self.assertEqual(s["vegetarian_orders"], 2)
        self.assertEqual(s["unanswered"], 2)
        self.assertEqual(s["base_portions"], 5)
        self.assertEqual(s["buffer"], 1)
        self.assertEqual(s["total_portions"], 6)

    def test_no_unanswered(self):
        orders = [{"dish": "A"}] * 5
        s = kitchen_summary(orders, 5, vegetarian_letters=set())
        self.assertEqual(s["unanswered"], 0)
        self.assertEqual(s["total_portions"], 6)

    def test_expected_less_than_orders(self):
        orders = [{"dish": "A"}] * 3
        s = kitchen_summary(orders, 2, vegetarian_letters=set())
        self.assertEqual(s["unanswered"], 0)


class TestBudgetStatus(unittest.TestCase):
    def test_ok(self):
        costs = {m["day"]: {"A": 100, "B": 120} for m in __import__("src.menu", fromlist=["get_menu"]).get_menu()}
        report = check_budget(costs)
        self.assertFalse(report["has_unknown"])
        self.assertFalse(report["has_over_limit"])

    def test_over(self):
        report = check_budget({"Понедельник": {"A": 150, "B": 120}})
        self.assertTrue(report["has_over_limit"])

    def test_unknown(self):
        report = check_budget({"Понедельник": {"A": None, "B": 120}})
        self.assertTrue(report["has_unknown"])
        self.assertFalse(report["has_over_limit"])


if __name__ == "__main__":
    unittest.main()
