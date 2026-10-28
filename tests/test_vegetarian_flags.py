# -*- coding: utf-8 -*-
"""Регрессионные тесты строгой интерпретации вегетарианских флагов."""

import os
import tempfile
import unittest

from domain.menu import MENU, get_active_menu, is_vegetarian_dish, vegetarian_letters_for_day
from repositories.storage import init_db, save_menu


class TestVegetarianFlags(unittest.TestCase):
    def test_true_and_false(self):
        menu = [dict(item) for item in MENU]
        menu[0]["dish_a_vegetarian"] = True
        menu[0]["dish_b_vegetarian"] = False
        self.assertTrue(is_vegetarian_dish("Понедельник", "A", menu=menu))
        self.assertFalse(is_vegetarian_dish("Понедельник", "B", menu=menu))
        self.assertEqual(vegetarian_letters_for_day("Понедельник", menu=menu), ["A"])

    def test_string_true_false_contract(self):
        menu = [dict(item) for item in MENU]
        menu[0]["dish_a_vegetarian"] = "true"
        menu[0]["dish_b_vegetarian"] = "false"
        self.assertTrue(is_vegetarian_dish("Понедельник", "A", menu=menu))
        self.assertFalse(is_vegetarian_dish("Понедельник", "B", menu=menu))
        self.assertEqual(vegetarian_letters_for_day("Понедельник", menu=menu), ["A"])

    def test_unsupported_value_not_truthy(self):
        menu = [dict(item) for item in MENU]
        menu[0]["dish_a_vegetarian"] = "not-a-bool"
        menu[0]["dish_b_vegetarian"] = 0
        with self.assertRaises(ValueError):
            is_vegetarian_dish("Понедельник", "A", menu=menu)
        with self.assertRaises(ValueError):
            vegetarian_letters_for_day("Понедельник", menu=menu)

    def test_consistent_between_functions(self):
        menu = [dict(item) for item in MENU]
        menu[0]["dish_a_vegetarian"] = "false"
        menu[0]["dish_b_vegetarian"] = "true"
        a = is_vegetarian_dish("Понедельник", "A", menu=menu)
        b = is_vegetarian_dish("Понедельник", "B", menu=menu)
        letters = vegetarian_letters_for_day("Понедельник", menu=menu)
        self.assertFalse(a)
        self.assertTrue(b)
        self.assertEqual(letters, ["B"])

    def test_builtin_menu_works(self):
        self.assertTrue(is_vegetarian_dish("Пятница", "A"))
        self.assertTrue(is_vegetarian_dish("Пятница", "B"))
        self.assertEqual(vegetarian_letters_for_day("Пятница"), ["A", "B"])

    def test_saved_menu_works(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        try:
            init_db(db)
            menu = [dict(item) for item in MENU]
            menu[0]["dish_a_vegetarian"] = "true"
            menu[0]["dish_b_vegetarian"] = "false"
            save_menu(menu, db_path=db)
            active = get_active_menu(db_path=db)
            self.assertTrue(is_vegetarian_dish("Понедельник", "A", menu=active))
            self.assertFalse(is_vegetarian_dish("Понедельник", "B", menu=active))
            self.assertEqual(vegetarian_letters_for_day("Понедельник", menu=active), ["A"])
        finally:
            if os.path.exists(db):
                os.remove(db)


if __name__ == "__main__":
    unittest.main()
