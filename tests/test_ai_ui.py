# -*- coding: utf-8 -*-
"""AppTest-проверка сохранения AI-меню в интерфейсе."""

import os
import tempfile
import unittest

import repositories.sqlite.storage as sqlite_storage
from domain.menu import MENU
from repositories.storage import get_saved_menu, init_db, save_menu
from streamlit.testing.v1 import AppTest
from ui.streamlit import main as ui_main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_APP = os.path.join(ROOT, "web_app.py")


class TestAIUI(unittest.TestCase):
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
            "get_ai_config": ui_main.get_ai_config,
            "get_active_menu": ui_main.get_active_menu,
            "generate_menu": ui_main.generate_menu,
            "save_menu": ui_main.save_menu,
        }

        ui_main.get_ai_config = lambda: {
            "provider": "mock",
            "model": "mock-model",
            "api_key": "test-key",
            "base_url": "http://mock",
            "configured": True,
        }
        ui_main.get_active_menu = lambda db_path=None: [dict(item) for item in MENU]

        self.result_menu = [dict(item) for item in MENU]
        self.result_menu[0]["dish_a"] = "AI dish"
        ui_main.generate_menu = lambda context=None, timeout=60: {
            "menu": [dict(item) for item in self.result_menu],
            "source": "ai",
            "provider": "mock",
            "model": "mock-model",
            "raw_text": "{}",
        }

        # По умолчанию успешное сохранение в временную БД.
        ui_main.save_menu = lambda menu, db_path=None: save_menu(menu, db_path=self.db)

        self.at = AppTest.from_file(WEB_APP, default_timeout=10)
        self.at.session_state["page"] = "AI-меню"
        self.at.run()

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(ui_main, name, value)
        sqlite_storage.DEFAULT_DB_PATH = self.original_default
        if os.path.exists(self.db):
            os.remove(self.db)

    def _click_button(self, label):
        for index, button in enumerate(self.at.button):
            if button.label == label:
                self.at.button[index].click().run()
                return
        raise KeyError(label)

    def _generate(self):
        self._click_button("Сформировать предложение меню")
        self.assertEqual(len(self.at.exception), 0)

    def test_save_error_shown_without_unhandled_exception(self):
        ui_main.save_menu = lambda menu, db_path=None: (_ for _ in ()).throw(
            ValueError("menu contains duplicate or invalid day")
        )

        self._generate()
        self._click_button("Сохранить как текущее меню")

        self.assertEqual(len(self.at.exception), 0)
        error_messages = [item.value for item in self.at.error]
        self.assertTrue(
            any("duplicate or invalid" in message for message in error_messages),
            error_messages,
        )
        success_messages = [item.value for item in self.at.success]
        self.assertFalse(
            any("Меню сохранено" in message for message in success_messages),
            success_messages,
        )
        # Приложение остаётся доступным: заголовок страницы присутствует.
        self.assertTrue(any("AI-меню" in title.value for title in self.at.title))

    def test_successful_save_available_in_ui(self):
        self._generate()
        self._click_button("Сохранить как текущее меню")

        self.assertEqual(len(self.at.exception), 0)
        success_messages = [item.value for item in self.at.success]
        self.assertTrue(
            any("Меню сохранено" in message for message in success_messages),
            success_messages,
        )
        saved = get_saved_menu(db_path=self.db)
        self.assertIsNotNone(saved)
        self.assertEqual(saved[0]["dish_a"], "AI dish")


if __name__ == "__main__":
    unittest.main()
