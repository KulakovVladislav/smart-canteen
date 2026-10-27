import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ai_menu import (
    generate_menu,
    is_configured,
    normalize_menu,
    parse_menu_response,
    validate_ai_menu,
)


class TestAIMenu(unittest.TestCase):
    def test_not_configured_by_default(self):
        os.environ.pop("AI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        self.assertFalse(is_configured())

    def test_generate_raises_without_key(self):
        os.environ.pop("AI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        with self.assertRaises(RuntimeError):
            generate_menu()

    def test_parse_json(self):
        text = '[{"day":"Понедельник","dish_a":"A","dish_b":"B","complaint_cluster":"x","dish_a_vegetarian":false,"dish_b_vegetarian":true}]'
        data = parse_menu_response(text)
        self.assertEqual(len(data), 1)

    def test_parse_markdown_fence(self):
        text = "```json\n[{\"day\":\"Пн\",\"dish_a\":\"A\",\"dish_b\":\"B\",\"complaint_cluster\":\"x\",\"dish_a_vegetarian\":false,\"dish_b_vegetarian\":true}]\n```"
        data = parse_menu_response(text)
        self.assertEqual(len(data), 1)

    def test_normalize(self):
        data = [{"day": "Пн", "dish_a": "A", "dish_b": "B", "complaint_cluster": "x", "dish_a_vegetarian": False, "dish_b_vegetarian": True}]
        menu = normalize_menu(data)
        self.assertEqual(menu[0]["day"], "Пн")
        self.assertTrue(menu[0]["dish_b_vegetarian"])

    def test_validate_ai_menu_missing_veg(self):
        menu = [{"day": "Пн", "dish_a": "A", "dish_b": "B", "complaint_cluster": "x", "dish_a_vegetarian": False, "dish_b_vegetarian": False}]
        ok, errors = validate_ai_menu(menu)
        self.assertFalse(ok)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
