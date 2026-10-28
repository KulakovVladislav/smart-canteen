# -*- coding: utf-8 -*-
"""AppTest-проверка подтверждений действий в Streamlit."""

import os
import tempfile
import unittest

import repositories.sqlite.storage as sqlite_storage
from domain.menu import MENU
from repositories.storage import get_dish_costs, init_db, save_dish_cost
from streamlit.testing.v1 import AppTest
from ui.streamlit import main as ui_main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_APP = os.path.join(ROOT, "web_app.py")


def _click_button(at, label):
    for index, button in enumerate(at.button):
        if button.label == label:
            at.button[index].click().run()
            return
    raise KeyError(label)


class TestActionFeedback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)

        self.original_default = sqlite_storage.DEFAULT_DB_PATH
        sqlite_storage.DEFAULT_DB_PATH = self.db
        init_db(self.db)

        self.originals = {
            "get_active_menu": ui_main.get_active_menu,
            "seed_demo_orders": ui_main.seed_demo_orders,
            "save_dish_cost": ui_main.save_dish_cost,
        }
        ui_main.get_active_menu = lambda db_path=None: [dict(item) for item in MENU]

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(ui_main, name, value)
        sqlite_storage.DEFAULT_DB_PATH = self.original_default
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_seed_orders_success_shown_and_not_duplicated(self):
        ui_main.seed_demo_orders = lambda meal_date, db_path=None: None

        at = AppTest.from_file(WEB_APP, default_timeout=10)
        at.session_state["page"] = "Кухня"
        at.run()
        _click_button(at, "Загрузить тестовые заказы на выбранную дату")

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Тестовые заказы добавлены" in s.value for s in at.success))
        # Повторный рендер не повторяет сообщение.
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertFalse(any("Тестовые заказы добавлены" in s.value for s in at.success))

    def test_seed_orders_error_shown(self):
        ui_main.seed_demo_orders = lambda meal_date, db_path=None: (_ for _ in ()).throw(
            RuntimeError("seed failed")
        )

        at = AppTest.from_file(WEB_APP, default_timeout=10)
        at.session_state["page"] = "Кухня"
        at.run()
        _click_button(at, "Загрузить тестовые заказы на выбранную дату")

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Не удалось загрузить тестовые заказы" in e.value for e in at.error))
        self.assertFalse(any("Тестовые заказы добавлены" in s.value for s in at.success))

    def test_costs_save_success_shown_and_not_duplicated(self):
        at = AppTest.from_file(WEB_APP, default_timeout=10)
        at.session_state["page"] = "Проверка бюджета"
        at.run()
        _click_button(at, "Сохранить стоимости")

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Стоимости сохранены локально" in s.value for s in at.success))
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertFalse(any("Стоимости сохранены локально" in s.value for s in at.success))

    def test_costs_save_error_shown(self):
        ui_main.save_dish_cost = lambda day, dish, cost, db_path=None: (_ for _ in ()).throw(
            ValueError("bad cost")
        )

        at = AppTest.from_file(WEB_APP, default_timeout=10)
        at.session_state["page"] = "Проверка бюджета"
        at.run()
        _click_button(at, "Сохранить стоимости")

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("bad cost" in e.value for e in at.error))
        self.assertFalse(any("Стоимости сохранены локально" in s.value for s in at.success))


if __name__ == "__main__":
    unittest.main()
