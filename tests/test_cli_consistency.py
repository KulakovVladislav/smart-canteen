# -*- coding: utf-8 -*-
"""Тесты согласованности CLI с активным меню."""

import contextlib
import io
import os
import tempfile
import unittest

import app
import repositories.sqlite.storage as sqlite_storage
from domain.menu import MENU
from repositories.storage import init_db, save_menu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCLIConsistency(unittest.TestCase):
    def _run(self, *args, db_path=None):
        original_default = sqlite_storage.DEFAULT_DB_PATH
        if db_path is not None:
            sqlite_storage.DEFAULT_DB_PATH = db_path
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = app.main(["app.py", *args])
        finally:
            sqlite_storage.DEFAULT_DB_PATH = original_default
        return code, buf.getvalue()

    def _temp_db(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        db = tmp.name
        if os.path.exists(db):
            os.remove(db)
        init_db(db)
        return db

    def test_fallback_builtin_menu_when_no_saved_menu(self):
        db = self._temp_db()
        try:
            code, out = self._run("menu", db_path=db)
            self.assertEqual(code, 0)
            self.assertIn("Каша без комков", out)
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_saved_menu_used_by_menu_command(self):
        db = self._temp_db()
        try:
            menu = [dict(item) for item in MENU]
            menu[0]["dish_a"] = "Специальное блюдо CLI"
            save_menu(menu, db_path=db)

            code, out = self._run("menu", db_path=db)
            self.assertEqual(code, 0)
            self.assertIn("Специальное блюдо CLI", out)
            self.assertNotIn("Каша без комков", out)
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_budget_check_uses_active_menu(self):
        db = self._temp_db()
        try:
            menu = [dict(item) for item in MENU]
            menu[0]["dish_a"] = "Блюдо для бюджета"
            save_menu(menu, db_path=db)

            code, out = self._run("budget-check", db_path=db)
            self.assertEqual(code, 0)
            self.assertIn("Потолок себестоимости", out)
            self.assertIn("Понедельник / A", out)
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_all_uses_consistent_active_menu(self):
        db = self._temp_db()
        try:
            menu = [dict(item) for item in MENU]
            menu[0]["dish_a"] = "Согласованное блюдо"
            save_menu(menu, db_path=db)

            code, out = self._run("all", db_path=db)
            self.assertEqual(code, 0)
            self.assertIn("Согласованное блюдо", out)
            self.assertIn("Потолок себестоимости", out)
        finally:
            if os.path.exists(db):
                os.remove(db)

    def test_existing_commands_still_work(self):
        db = self._temp_db()
        try:
            code, out = self._run("preorder", db_path=db)
            self.assertEqual(code, 0)
            self.assertIn("Порций блюда A:", out)
            code, out = self._run("nope", db_path=db)
            self.assertEqual(code, 2)
        finally:
            if os.path.exists(db):
                os.remove(db)


if __name__ == "__main__":
    unittest.main()
