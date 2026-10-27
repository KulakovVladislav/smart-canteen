import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.preorder import count_preorders, format_summary, SAMPLE_PREORDERS


class TestPreorder(unittest.TestCase):
    def test_counts_basic(self):
        res = count_preorders(["A", "A", "B", None, "B", "X"])
        self.assertEqual(res["a"], 2)
        self.assertEqual(res["b"], 2)
        self.assertEqual(res["unanswered"], 2)
        self.assertEqual(res["total_students"], 6)

    def test_buffer_math(self):
        res = count_preorders(["A"] * 10)
        self.assertEqual(res["base_portions"], 10)
        self.assertEqual(res["buffer"], 1)
        self.assertEqual(res["total"], 11)

    def test_buffer_100(self):
        res = count_preorders(["A"] * 100)
        self.assertEqual(res["buffer"], 5)
        self.assertEqual(res["total"], 105)

    def test_empty_input(self):
        res = count_preorders([])
        self.assertEqual(res["total_students"], 0)
        self.assertEqual(res["total"], 0)
        self.assertEqual(res["unanswered"], 0)

    def test_none_input(self):
        res = count_preorders(None)
        self.assertEqual(res["total_students"], 0)
        self.assertEqual(res["total"], 0)

    def test_all_b_vegetarian(self):
        res = count_preorders(["B", "B", "B"])
        self.assertEqual(res["vegetarian"], 3)
        self.assertEqual(res["b_portions"], 3)

    def test_dict_choices(self):
        res = count_preorders([{"choice": "A"}, {"choice": "b"}, {"answer": None}])
        self.assertEqual(res["a"], 1)
        self.assertEqual(res["b"], 1)
        self.assertEqual(res["unanswered"], 1)

    def test_default_choice_b(self):
        res = count_preorders([None, None], default_choice="B")
        self.assertEqual(res["b_portions"], 2)
        self.assertEqual(res["a_portions"], 0)

    def test_format_summary_contains_keys(self):
        text = format_summary(count_preorders(SAMPLE_PREORDERS))
        self.assertIn("Порций блюда A:", text)
        self.assertIn("Итого порций к приготовлению:", text)

    def test_invalid_not_crash(self):
        res = count_preorders([123, "Z", "", None])
        self.assertEqual(res["total_students"], 4)
        self.assertGreaterEqual(res["total"], 4)


if __name__ == "__main__":
    unittest.main()
