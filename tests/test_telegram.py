# -*- coding: utf-8 -*-
"""Проверки Telegram-бота: роли, кнопки, тексты и сценарии."""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.telegram_bot as tb
from src.storage import (
    get_leftovers,
    get_orders,
    get_subscribers,
    init_db,
    save_leftover,
    save_order,
    subscribe_chat,
)


class TelegramTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)
        init_db(self.db)

        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        self.addCleanup(self._env.stop)
        os.environ.pop("TELEGRAM_ADMIN_IDS", None)
        os.environ["CANTEEN_EXPECTED_DINERS"] = "500"
        tb._LEFTOVER_PENDING.clear()

    def tearDown(self):
        tb._LEFTOVER_PENDING.clear()
        if os.path.exists(self.db):
            os.remove(self.db)

    def set_admin(self, *user_ids):
        os.environ["TELEGRAM_ADMIN_IDS"] = ",".join(str(x) for x in user_ids)

    @staticmethod
    def target_date():
        return tb.next_school_day()


class InteractionTest(TelegramTestBase):
    """Тесты, где нужно проверить отправленные тексты и клавиатуры."""

    def setUp(self):
        super().setUp()
        self.sent = []
        self.answers = []
        patches = [
            mock.patch.object(tb, "send_message", side_effect=self._capture_message),
            mock.patch.object(tb, "send_photo", side_effect=self._capture_photo),
            mock.patch.object(tb, "answer_callback", side_effect=self._capture_answer),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _capture_message(self, token, chat_id, text, reply_markup=None, parse_mode="HTML", timeout=30):
        self.sent.append(
            {"kind": "message", "chat_id": chat_id, "text": text, "keyboard": reply_markup}
        )
        return {"message_id": len(self.sent)}

    def _capture_photo(self, token, chat_id, photo, caption=None, reply_markup=None, parse_mode="HTML", timeout=30):
        self.sent.append(
            {"kind": "photo", "chat_id": chat_id, "text": caption, "keyboard": reply_markup, "photo": photo}
        )
        return {"message_id": len(self.sent)}

    def _capture_answer(self, token, callback_query_id, text=None, timeout=30):
        self.answers.append({"id": callback_query_id, "text": text})
        return True

    @staticmethod
    def callback(data, user_id=5, chat_id=None):
        return {
            "callback_query": {
                "id": "cb-1",
                "from": {"id": user_id},
                "message": {"chat": {"id": chat_id if chat_id is not None else user_id}},
                "data": data,
            }
        }

    @staticmethod
    def message(text, user_id=5, chat_id=None):
        return {
            "message": {
                "chat": {"id": chat_id if chat_id is not None else user_id},
                "from": {"id": user_id},
                "text": text,
            }
        }

    def send(self, update):
        tb.handle_update(update, token="T", db_path=self.db)

    def last_text(self):
        self.assertTrue(self.sent, "бот ничего не отправил")
        return self.sent[-1]["text"] or ""

    def last_keyboard(self):
        return json.dumps(self.sent[-1]["keyboard"], ensure_ascii=False)

    def assert_keyboard_has(self, value):
        self.assertIn(value, self.last_keyboard())

    def assert_keyboard_lacks(self, value):
        self.assertNotIn(value, self.last_keyboard())


class TestRoles(InteractionTest):
    def test_student_keyboard_has_only_student_actions(self):
        text = json.dumps(tb.build_main_keyboard(False), ensure_ascii=False)
        self.assertIn("Заказать обед", text)
        self.assertIn("Мой заказ", text)
        self.assertIn("nav:order", text)
        self.assertIn("nav:myorder", text)
        self.assertNotIn("Сводка", text)
        self.assertNotIn("Остатки", text)

    def test_staff_main_keyboard_has_kitchen_buttons_and_no_order(self):
        kb = tb.build_main_keyboard(True)
        text = json.dumps(kb, ensure_ascii=False)
        self.assertIn("Сводка", text)
        self.assertIn("Внести остатки", text)
        self.assertNotIn("Заказать обед", text)
        self.assertNotIn("nav:myorder", text)

    def test_main_keyboard_has_no_redundant_home_button(self):
        for is_admin in (False, True):
            text = json.dumps(tb.build_main_keyboard(is_admin), ensure_ascii=False)
            self.assertNotIn("nav:home", text)

    def test_student_start_subscribes_and_opens_order_actions(self):
        self.send(self.message("/start"))
        self.assertIn("бот предзаказа", self.last_text())
        self.assertIn("5", get_subscribers(db_path=self.db))
        self.assert_keyboard_has("nav:order")

    def test_staff_start_has_no_student_actions(self):
        self.set_admin(9)
        self.send(self.message("/start", user_id=9))
        self.assert_keyboard_has("nav:summary")
        self.assert_keyboard_has("nav:leftover")
        self.assert_keyboard_lacks("nav:order")
        self.assert_keyboard_lacks("nav:myorder")
        self.assertIn("сотрудников кухни", self.last_text())

    def test_student_help_explains_bot_order(self):
        self.send(self.message("/help"))
        self.assertIn("Как оформить предзаказ", self.last_text())
        self.assertIn("/order", self.last_text())

    def test_staff_help_is_staff_specific(self):
        self.set_admin(9)
        self.send(self.message("/help", user_id=9))
        text = self.last_text()
        self.assertIn("/summary", text)
        self.assertIn("/leftover", text)
        self.assertNotIn("/order", text)
        self.assertIn("Предзаказ ученики оформляют в этом Telegram-боте", text)

    def test_student_order_command_opens_order_flow(self):
        self.set_admin(9)
        self.send(self.message("/order", user_id=5))
        self.assertEqual(len(get_orders(self.target_date().isoformat(), db_path=self.db)), 0)
        self.assertIn("Заказ на", self.last_text())
        self.assert_keyboard_has("order:")

    def test_commands_are_role_specific(self):
        student = {c["command"] for c in tb.build_commands(False)}
        staff = {c["command"] for c in tb.build_commands(True)}
        self.assertTrue({"start", "menu", "order", "myorder", "cancel", "stop", "help"}.issubset(student))
        self.assertIn("summary", staff)
        self.assertIn("leftover", staff)
        self.assertNotIn("order", staff)


class TestStaffKitchen(InteractionTest):
    def test_staff_menu_is_readonly(self):
        self.set_admin(9)
        self.send(self.callback("nav:menu", user_id=9))
        self.assertIn("только просмотр", self.last_text())
        self.assert_keyboard_lacks("order:")
        self.assert_keyboard_lacks("cancel:")
        self.assert_keyboard_has("nav:summary")

    def test_staff_menu_does_not_create_order(self):
        self.set_admin(9)
        self.send(self.message("/menu", user_id=9))
        self.assertEqual(len(get_orders(db_path=self.db)), 0)
        self.assert_keyboard_lacks("order:")

    def test_leftover_pending_flow_saves_and_clears(self):
        self.set_admin(9)
        self.send(self.callback("nav:leftover", user_id=9))
        self.assertTrue(tb._leftover_is_pending(9))
        self.send(self.message("1,5 2 после обеда", user_id=9))
        rows = get_leftovers(db_path=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["waste_mass_kg"], 1.5)
        self.assertEqual(rows[0]["leftover_portions"], 2)
        self.assertEqual(rows[0]["note"], "после обеда")
        self.assertFalse(tb._leftover_is_pending(9))
        self.assertIn("Остатки сохранены", self.last_text())
        self.assertNotIn("  \n", self.last_text())

    def test_leftover_cancel_button_clears_pending(self):
        self.set_admin(9)
        self.send(self.callback("nav:leftover", user_id=9))
        self.send(self.callback("leftover:cancel", user_id=9))
        self.assertFalse(tb._leftover_is_pending(9))
        self.assertIn("отменён", self.last_text())

    def test_admin_cancel_clears_leftover_mode(self):
        self.set_admin(9)
        self.send(self.callback("nav:leftover", user_id=9))
        self.send(self.message("/cancel", user_id=9))
        self.assertFalse(tb._leftover_is_pending(9))
        self.assertIn("Ввод остатков отменён", self.last_text())
        self.send(self.message("1 2", user_id=9))
        self.assertEqual(len(get_leftovers(db_path=self.db)), 0)

    def test_leftover_command_with_args(self):
        self.set_admin(9)
        self.send(self.message("/leftover 2.5 3 note", user_id=9))
        rows = get_leftovers(db_path=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["waste_mass_kg"], 2.5)
        self.assertEqual(rows[0]["leftover_portions"], 3)

    def test_leftover_command_without_args_starts_pending(self):
        self.set_admin(9)
        self.send(self.message("/leftover", user_id=9))
        self.assertTrue(tb._leftover_is_pending(9))
        self.assert_keyboard_has("leftover:cancel")

    def test_leftover_invalid_not_saved(self):
        self.set_admin(9)
        self.send(self.message("/leftover -1 2", user_id=9))
        self.assertEqual(len(get_leftovers(db_path=self.db)), 0)
        self.assertIn("Не получилось сохранить", self.last_text())

    def test_leftover_history_empty(self):
        self.set_admin(9)
        self.send(self.callback("nav:leftovers", user_id=9))
        self.assertIn("Записей пока нет", self.last_text())

    def test_leftover_history_lists_rows(self):
        self.set_admin(9)
        save_leftover("2026-10-28", 1.5, 2, "первая", db_path=self.db)
        save_leftover("2026-10-29", 0.5, 1, "", db_path=self.db)
        self.send(self.callback("nav:leftovers", user_id=9))
        text = self.last_text()
        self.assertIn("Последние остатки", text)
        self.assertIn("1.5 кг", text)
        self.assertIn("первая", text)
        self.assert_keyboard_has("nav:leftover")

    def test_summary_counts_orders(self):
        self.set_admin(9)
        today = date.today().isoformat()
        save_order("TG-1", today, "A", db_path=self.db)
        save_order("TG-2", today, "B", db_path=self.db)
        self.send(self.callback("nav:summary", user_id=9))
        text = self.last_text()
        self.assertIn("Заказов A: <b>1</b>", text)
        self.assertIn("Заказов B: <b>1</b>", text)
        self.assertIn("Всего заказов: <b>2</b>", text)
        self.assert_keyboard_has("nav:leftover")

    def test_summary_specific_date(self):
        self.set_admin(9)
        target = self.target_date()
        save_order("TG-1", target.isoformat(), "A", db_path=self.db)
        self.send(self.message(f"/summary {target.isoformat()}", user_id=9))
        self.assertIn("Заказов A: <b>1</b>", self.last_text())

    def test_summary_invalid_date(self):
        self.set_admin(9)
        self.send(self.message("/summary 2026-13-99", user_id=9))
        self.assertIn("Неверный формат даты", self.last_text())

    def test_summary_empty_state(self):
        self.set_admin(9)
        self.send(self.callback("nav:summary", user_id=9))
        self.assertIn("Заказов пока нет", self.last_text())


class TestInteractionBasics(InteractionTest):
    def test_staff_start_subscribes_chat(self):
        self.set_admin(5)
        self.send(self.message("/start", user_id=5))
        self.assertIn("5", get_subscribers(db_path=self.db))

    def test_staff_can_disable_broadcasts(self):
        self.set_admin(5)
        self.send(self.message("/start", user_id=5))
        self.send(self.message("/stop", user_id=5))
        self.assertNotIn("5", get_subscribers(db_path=self.db))
        self.assertIn("отключена", self.last_text())

    def test_unknown_command_suggests_help(self):
        self.send(self.message("/unknown"))
        self.assertIn("Неизвестная команда", self.last_text())

    def test_plain_text_shows_actions(self):
        self.send(self.message("привет"))
        self.assertIn("Выберите действие", self.last_text())
        self.assert_keyboard_has("nav:order")

    def test_non_text_message_gets_hint(self):
        self.send({"message": {"chat": {"id": 5}, "from": {"id": 5}}})
        self.assertIn("Нажмите /help", self.last_text())

    def test_unknown_callback_returns_home(self):
        self.send(self.callback("legacy:button"))
        self.assertIn("кнопка устарела", self.last_text())
        self.assert_keyboard_has("nav:order")

    def test_callback_is_answered(self):
        self.send(self.callback("nav:menu"))
        self.assertEqual(self.answers[-1]["id"], "cb-1")

    def test_empty_update_does_not_crash(self):
        tb.handle_update({}, token=None, db_path=self.db)
        tb.handle_update(None, token=None, db_path=self.db)


class TestBroadcast(InteractionTest):
    def test_broadcast_marks_existing_choice(self):
        target = self.target_date()
        subscribe_chat("42", db_path=self.db)
        save_order("TG-42", target.isoformat(), "A", db_path=self.db)
        sent = tb.broadcast_menu("T", meal_date=target, db_path=self.db)
        self.assertEqual(sent, 1)
        self.assertIn("Ваш выбор", self.last_text())
        self.assert_keyboard_has(f"order:{target.isoformat()}:B")
        self.assert_keyboard_has("✅ A")

    def test_broadcast_admin_is_readonly(self):
        self.set_admin(9)
        subscribe_chat("9", db_path=self.db)
        sent = tb.broadcast_menu("T", meal_date=self.target_date(), db_path=self.db)
        self.assertEqual(sent, 1)
        self.assertIn("только просмотр", self.last_text())
        self.assert_keyboard_lacks("order:")

    def test_broadcast_without_subscribers(self):
        self.assertEqual(tb.broadcast_menu("T", meal_date=self.target_date(), db_path=self.db), 0)


if __name__ == "__main__":
    unittest.main()
