import os
import tempfile
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.storage import init_db
from src.telegram_bot import handle_update, is_admin, next_school_day


class TestTelegram(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = self.tmp.name
        if os.path.exists(self.db):
            os.remove(self.db)
        init_db(self.db)
        os.environ.pop("TELEGRAM_ADMIN_IDS", None)

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_next_school_day_weekend(self):
        # Friday -> Monday
        fri = date(2026, 10, 30)  # Friday
        self.assertEqual(next_school_day(fri).weekday(), 0)

    def test_is_admin_false_by_default(self):
        self.assertFalse(is_admin(123))

    def test_is_admin_from_env(self):
        os.environ["TELEGRAM_ADMIN_IDS"] = "123, 456"
        self.assertTrue(is_admin(123))
        self.assertFalse(is_admin(999))

    def test_handle_update_order_saves(self):
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
        self.assertEqual(orders[0]["dish"], "A")

    def test_handle_update_upsert(self):
        upd1 = {"callback_query": {"id": "1", "from": {"id": 1}, "message": {"chat": {"id": 1}},
                                   "data": "order:2026-11-02:A"}}
        upd2 = {"callback_query": {"id": "2", "from": {"id": 1}, "message": {"chat": {"id": 1}},
                                   "data": "order:2026-11-02:B"}}
        handle_update(upd1, token=None, db_path=self.db)
        handle_update(upd2, token=None, db_path=self.db)
        from src.storage import get_orders

        orders = [o for o in get_orders("2026-11-02", db_path=self.db) if o["student_code"] == "TG-1"]
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["dish"], "B")


if __name__ == "__main__":
    unittest.main()
