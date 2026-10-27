# -*- coding: utf-8 -*-
"""Regression tests for phase 0: storage, menu, waste, telegram."""

import os
import tempfile
import unittest
from datetime import date

from src.menu import (
    MENU,
    get_active_menu,
    is_vegetarian_dish,
    vegetarian_letters_for_day,
)
from src.storage import (
    get_dish_costs,
    get_leftovers,
    init_db,
    reset_demo_data,
    save_dish_cost,
    save_leftover,
    save_menu,
)
from src.waste_calc import load_waste
from src.telegram_bot import handle_update


class TestActiveMenuVegetarian(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)
        init_db(self.db)

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_vegetarian_from_saved_menu(self):
        menu = [dict(item) for item in MENU]
        menu[0]["dish_b_vegetarian"] = True
        menu[0]["dish_a_vegetarian"] = False
        save_menu(menu, db_path=self.db)
        active = get_active_menu(db_path=self.db)
        self.assertEqual(active[0]["day"], "Понедельник")
        self.assertFalse(active[0]["dish_a_vegetarian"])
        self.assertTrue(active[0]["dish_b_vegetarian"])
        self.assertTrue(is_vegetarian_dish("Понедельник", "B", menu=active))
        self.assertFalse(is_vegetarian_dish("Понедельник", "A", menu=active))
        self.assertEqual(vegetarian_letters_for_day("Понедельник", menu=active), ["B"])

    def test_vegetarian_default_menu(self):
        self.assertTrue(is_vegetarian_dish("Пятница", "A"))
        self.assertTrue(is_vegetarian_dish("Пятница", "B"))
        self.assertEqual(vegetarian_letters_for_day("Пятница"), ["A", "B"])


class TestStorageLimitAndCost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)
        init_db(self.db)

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_limit_zero_returns_none(self):
        save_leftover("2026-10-28", 1.0, 1, db_path=self.db)
        rows = get_leftovers(db_path=self.db, limit=0)
        self.assertEqual(rows, [])

    def test_limit_negative_raises(self):
        with self.assertRaises(ValueError):
            get_leftovers(db_path=self.db, limit=-1)

    def test_invalid_cost_raises(self):
        with self.assertRaises(ValueError):
            save_dish_cost("Понедельник", "A", "abc", db_path=self.db)

    def test_invalid_cost_handled_in_web(self):
        # save_dish_cost must raise ValueError, not silently zero
        with self.assertRaises(ValueError):
            save_dish_cost("Понедельник", "A", "not-a-number", db_path=self.db)


class TestWasteCsvValidation(unittest.TestCase):
    def test_missing_file_raises(self):
        import src.waste_calc as wc

        original = wc.CSV_PATH
        wc.CSV_PATH = "/nonexistent/path/waste_by_day.csv"
        try:
            with self.assertRaises((FileNotFoundError, ValueError)):
                wc.load_waste()
        finally:
            wc.CSV_PATH = original

    def test_bad_column_raises(self):
        import csv
        import src.waste_calc as wc

        d = tempfile.mkdtemp()
        path = os.path.join(d, "waste_by_day.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["day", "wrong_col"])
            writer.writerow(["Понедельник", "10"])
        original = wc.CSV_PATH
        wc.CSV_PATH = path
        try:
            with self.assertRaises((FileNotFoundError, ValueError)):
                wc.load_waste()
        finally:
            wc.CSV_PATH = original


class TestTelegramDateValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)
        init_db(self.db)

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_invalid_date_not_saved(self):
        upd = {
            "callback_query": {
                "id": "1",
                "from": {"id": 777},
                "message": {"chat": {"id": 777}},
                "data": "order:not-a-date:A",
            }
        }
        handle_update(upd, token=None, db_path=self.db)
        from src.storage import get_orders

        self.assertEqual(len(get_orders("not-a-date", db_path=self.db)), 0)

    def test_valid_date_saved(self):
        upd = {
            "callback_query": {
                "id": "1",
                "from": {"id": 777},
                "message": {"chat": {"id": 777}},
                "data": "order:2026-11-02:A",
            }
        }
        handle_update(upd, token=None, db_path=self.db)
        from src.storage import get_orders

        orders = [o for o in get_orders("2026-11-02", db_path=self.db) if o["student_code"] == "TG-777"]
        self.assertEqual(len(orders), 1)


class TestInitDbIdempotent(unittest.TestCase):
    def test_repeated_init(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        try:
            init_db(db)
            init_db(db)
            init_db(db)
        finally:
            if os.path.exists(db):
                os.remove(db)


if __name__ == "__main__":
    unittest.main()