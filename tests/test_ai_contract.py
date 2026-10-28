# -*- coding: utf-8 -*-
"""Регрессионные тесты контракта AI-меню и сохранения меню."""

import os
import sqlite3
import tempfile
import unittest

import repositories.sqlite.storage as sqlite_storage
from domain.menu import DAY_NAMES, MENU, get_active_menu, validate_menu
from repositories.storage import get_saved_menu, init_db, save_menu
from services.ai_menu import normalize_menu, parse_menu_response, validate_ai_menu


def _valid_ai_json():
    return (
        '[{"day":"Понедельник","dish_a":"A","dish_b":"B","complaint_cluster":"x",'
        '"dish_a_vegetarian":false,"dish_b_vegetarian":true},'
        '{"day":"Вторник","dish_a":"C","dish_b":"D","complaint_cluster":"",'
        '"dish_a_vegetarian":false,"dish_b_vegetarian":false},'
        '{"day":"Среда","dish_a":"E","dish_b":"F","complaint_cluster":"y",'
        '"dish_a_vegetarian":true,"dish_b_vegetarian":false},'
        '{"day":"Четверг","dish_a":"G","dish_b":"H","complaint_cluster":"z",'
        '"dish_a_vegetarian":false,"dish_b_vegetarian":true},'
        '{"day":"Пятница","dish_a":"I","dish_b":"J","complaint_cluster":"w",'
        '"dish_a_vegetarian":true,"dish_b_vegetarian":true}]'
    )


class TestAIContract(unittest.TestCase):
    def test_valid_json_five_days_accepted_and_saved(self):
        data = parse_menu_response(_valid_ai_json())
        self.assertEqual(len(data), 5)
        menu = normalize_menu(data)
        ok, errors = validate_menu(menu)
        self.assertTrue(ok, errors)
        ok2, errors2 = validate_ai_menu(menu)
        self.assertTrue(ok2, errors2)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        try:
            init_db(db)
            save_menu(menu, db_path=db)
            saved = get_saved_menu(db_path=db)
            self.assertIsNotNone(saved)
            self.assertEqual([item["day"] for item in saved], DAY_NAMES)
            active = get_active_menu(db_path=db)
            self.assertEqual([item["day"] for item in active], DAY_NAMES)
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_markdown_table_rejected(self):
        table = "| День | Блюдо A | Блюдо B |\n|---|---|---|\n| Понедельник | A | B |"
        with self.assertRaises(ValueError):
            parse_menu_response(table)

    def test_missing_fields_and_null_rejected(self):
        base = {
            "day": "Понедельник",
            "dish_a": "A",
            "dish_b": "B",
            "complaint_cluster": "x",
            "dish_a_vegetarian": False,
            "dish_b_vegetarian": True,
        }
        for field in ("day", "dish_a", "dish_b", "complaint_cluster"):
            item = dict(base)
            item.pop(field)
            with self.assertRaises(ValueError):
                normalize_menu([item])
        for field in ("day", "dish_a", "dish_b"):
            item = dict(base)
            item[field] = None
            with self.assertRaises(ValueError):
                normalize_menu([item])
        item = dict(base)
        item["complaint_cluster"] = None
        with self.assertRaises(ValueError):
            normalize_menu([item])

    def test_real_booleans_accepted_strings_not_silently_bool(self):
        data = parse_menu_response(
            '[{"day":"Понедельник","dish_a":"A","dish_b":"B","complaint_cluster":"x",'
            '"dish_a_vegetarian":false,"dish_b_vegetarian":true}]'
        )
        menu = normalize_menu(data)
        self.assertIs(menu[0]["dish_a_vegetarian"], False)
        self.assertIs(menu[0]["dish_b_vegetarian"], True)

        # Строка "false" не должна давать True через bool(); строгий разбор даёт False.
        menu2 = normalize_menu(
            [
                {
                    "day": "Понедельник",
                    "dish_a": "A",
                    "dish_b": "B",
                    "complaint_cluster": "x",
                    "dish_a_vegetarian": "false",
                    "dish_b_vegetarian": "true",
                }
            ]
        )
        self.assertIs(menu2[0]["dish_a_vegetarian"], False)
        self.assertIs(menu2[0]["dish_b_vegetarian"], True)

        with self.assertRaises(ValueError):
            normalize_menu(
                [
                    {
                        "day": "Понедельник",
                        "dish_a": "A",
                        "dish_b": "B",
                        "complaint_cluster": "x",
                        "dish_a_vegetarian": "not-a-bool",
                        "dish_b_vegetarian": True,
                    }
                ]
            )

    def test_duplicate_unknown_wrong_order_rejected(self):
        base_item = {
            "dish_a": "A",
            "dish_b": "B",
            "complaint_cluster": "x",
            "dish_a_vegetarian": False,
            "dish_b_vegetarian": True,
        }
        # wrong order
        wrong_order = [{"day": d, **base_item} for d in ["Вторник", "Понедельник", "Среда", "Четверг", "Пятница"]]
        with self.assertRaises(ValueError):
            normalize_menu(wrong_order)
        ok, errors = validate_menu(wrong_order)
        self.assertFalse(ok)

        # duplicate day
        duplicate = [{"day": "Понедельник", **base_item} for _ in range(5)]
        with self.assertRaises(ValueError):
            normalize_menu(duplicate)
        ok, errors = validate_menu(duplicate)
        self.assertFalse(ok)

        # unknown day
        unknown = [{"day": "Суббота", **base_item} for _ in range(5)]
        # normalize rejects on first item
        with self.assertRaises(ValueError):
            normalize_menu(unknown)
        ok, errors = validate_menu(unknown)
        self.assertFalse(ok)

    def test_empty_complaint_cluster_allowed(self):
        menu = [dict(item) for item in MENU]
        menu[0]["complaint_cluster"] = "   "
        ok, errors = validate_menu(menu)
        self.assertTrue(ok, errors)
        menu2 = [dict(item) for item in MENU]
        menu2[0]["complaint_cluster"] = ""
        ok2, errors2 = validate_menu(menu2)
        self.assertTrue(ok2, errors2)

    def test_menu_without_vegetarian_not_rejected_for_that_reason(self):
        menu = [dict(item) for item in MENU]
        for item in menu:
            item["dish_a_vegetarian"] = False
            item["dish_b_vegetarian"] = False
        ok, errors = validate_menu(menu)
        self.assertTrue(ok, errors)

    def test_invalid_menu_not_saved_to_sqlite(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        try:
            init_db(db)
            invalid_menu = [dict(item) for item in MENU]
            invalid_menu[0]["dish_a"] = ""
            with self.assertRaises(ValueError):
                save_menu(invalid_menu, db_path=db)
            self.assertIsNone(get_saved_menu(db_path=db))
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_integrity_error_handled_predictably(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        original_validate = sqlite_storage.validate_menu
        try:
            init_db(db)
            sqlite_storage.validate_menu = lambda menu: (True, [])
            duplicate_day_menu = [dict(item) for item in MENU]
            duplicate_day_menu[1]["day"] = duplicate_day_menu[0]["day"]
            with self.assertRaises(ValueError) as ctx:
                save_menu(duplicate_day_menu, db_path=db)
            self.assertIn("duplicate or invalid", str(ctx.exception))
        finally:
            sqlite_storage.validate_menu = original_validate
            if os.path.exists(db):
                os.remove(db)

    def test_saved_menu_retrievable_via_active_menu(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        try:
            init_db(db)
            menu = [dict(item) for item in MENU]
            menu[0]["dish_a"] = "Специальное блюдо"
            save_menu(menu, db_path=db)
            active = get_active_menu(db_path=db)
            self.assertEqual(active[0]["dish_a"], "Специальное блюдо")
            saved = get_saved_menu(db_path=db)
            self.assertIsNotNone(saved)
            self.assertEqual(saved[0]["dish_a"], "Специальное блюдо")
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_save_menu_normalizes_vegetarian_flags(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        try:
            init_db(db)
            menu = [dict(item) for item in MENU]
            menu[0]["dish_a_vegetarian"] = "false"
            menu[0]["dish_b_vegetarian"] = "true"
            save_menu(menu, db_path=db)

            saved = get_saved_menu(db_path=db)
            self.assertIsNotNone(saved)
            self.assertIs(saved[0]["dish_a_vegetarian"], False)
            self.assertIs(saved[0]["dish_b_vegetarian"], True)

            unsupported = [dict(item) for item in MENU]
            unsupported[0]["dish_a_vegetarian"] = "not-a-bool"
            with self.assertRaises(ValueError):
                save_menu(unsupported, db_path=db)
        finally:
            if os.path.exists(db):
                os.remove(db)


if __name__ == "__main__":
    unittest.main()
