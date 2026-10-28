# -*- coding: utf-8 -*-
"""Регрессионные тесты очистки демонстрационных данных (аудит P2-2)."""

import os
import tempfile
import unittest

import repositories.sqlite.storage as sqlite_storage
from domain.menu import MENU
from repositories.storage import (
    get_dish_costs,
    get_leftovers,
    get_orders,
    get_saved_menu,
    init_db,
    reset_demo_data,
    save_dish_cost,
    save_leftover,
    save_menu,
    save_order,
)

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover - зависит от окружения
    AppTest = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_APP = os.path.join(ROOT, "web_app.py")


def _custom_menu():
    menu = [dict(item) for item in MENU]
    menu[0]["dish_a"] = "Тестовое блюдо после сброса"
    return menu


class TestResetDemoDataStorage(unittest.TestCase):
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

    def test_reset_clears_orders_costs_leftovers_and_keeps_saved_menu(self):
        save_order("TEST-001", "2026-10-28", "A", db_path=self.db)
        save_dish_cost("Понедельник", "A", 120, db_path=self.db)
        save_leftover("2026-10-28", 1.5, 2, "тест", db_path=self.db)
        menu = _custom_menu()
        save_menu(menu, db_path=self.db)

        reset_demo_data(db_path=self.db)

        self.assertEqual(get_orders(db_path=self.db), [])
        self.assertEqual(get_dish_costs(db_path=self.db), {})
        self.assertEqual(get_leftovers(db_path=self.db), [])

        saved = get_saved_menu(db_path=self.db)
        self.assertIsNotNone(saved)
        self.assertEqual(saved[0]["dish_a"], "Тестовое блюдо после сброса")


@unittest.skipUnless(AppTest is not None, "Streamlit AppTest недоступен")
class TestResetDemoDataUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)

        self.original_default = sqlite_storage.DEFAULT_DB_PATH
        sqlite_storage.DEFAULT_DB_PATH = self.db

        init_db(self.db)
        save_order("TEST-001", "2026-10-28", "A", db_path=self.db)
        save_dish_cost("Понедельник", "A", 120, db_path=self.db)
        save_leftover("2026-10-28", 1.5, 2, "тест", db_path=self.db)
        save_menu(_custom_menu(), db_path=self.db)

        self.at = AppTest.from_file(WEB_APP, default_timeout=10)
        self.at.session_state["page"] = "Кухня"
        self.at.run()

    def tearDown(self):
        sqlite_storage.DEFAULT_DB_PATH = self.original_default
        if os.path.exists(self.db):
            os.remove(self.db)

    def _assert_data_seeded(self):
        self.assertEqual(len(get_orders(db_path=self.db)), 1)
        self.assertEqual(len(get_dish_costs(db_path=self.db)), 1)
        self.assertEqual(len(get_leftovers(db_path=self.db)), 1)

    def _assert_data_cleared(self):
        self.assertEqual(get_orders(db_path=self.db), [])
        self.assertEqual(get_dish_costs(db_path=self.db), {})
        self.assertEqual(get_leftovers(db_path=self.db), [])
        saved = get_saved_menu(db_path=self.db)
        self.assertIsNotNone(saved)
        self.assertEqual(saved[0]["dish_a"], "Тестовое блюдо после сброса")

    def test_reset_requires_confirmation(self):
        self._assert_data_seeded()
        self.assertFalse(self.at.checkbox(key="reset_confirmed").value)
        self.assertTrue(self.at.button(key="reset_demo_data").disabled)

        # Без подтверждения кнопка недоступна, данные остаются на месте.
        self.at.run()
        self._assert_data_seeded()

    def test_confirmed_reset_clears_data_without_widget_error(self):
        self.at.checkbox(key="reset_confirmed").check().run()
        self.assertFalse(self.at.button(key="reset_demo_data").disabled)

        self.at.button(key="reset_demo_data").click().run()

        self.assertEqual(len(self.at.exception), 0)
        self._assert_data_cleared()
        self.assertFalse(self.at.checkbox(key="reset_confirmed").value)
        self.assertTrue(self.at.button(key="reset_demo_data").disabled)
        success_messages = [item.value for item in self.at.success]
        self.assertTrue(
            any(
                "заказы, стоимости блюд и остатки" in message
                and "Сохранённое меню не изменено" in message
                for message in success_messages
            ),
            success_messages,
        )

    def test_repeated_render_does_not_repeat_reset(self):
        self.at.checkbox(key="reset_confirmed").check().run()
        self.at.button(key="reset_demo_data").click().run()
        self._assert_data_cleared()

        save_order("TEST-002", "2026-10-29", "B", db_path=self.db)
        self.at.run()

        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(len(get_orders(db_path=self.db)), 1)
        reset_messages = [m for m in (item.value for item in self.at.success)
                          if "заказы, стоимости блюд и остатки" in m]
        self.assertEqual(reset_messages, [])


if __name__ == "__main__":
    unittest.main()
