import os
import tempfile
import unittest

from src.storage import (
    count_orders,
    get_orders,
    init_db,
    reset_demo_data,
    save_dish_cost,
    save_order,
    get_dish_costs,
)


class TestStorage(unittest.TestCase):
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

    def test_save_and_get_order(self):
        save_order("TEST-001", "2026-10-28", "A", db_path=self.db)
        orders = get_orders("2026-10-28", db_path=self.db)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["dish"], "A")

    def test_upsert_order(self):
        save_order("TEST-001", "2026-10-28", "A", db_path=self.db)
        save_order("TEST-001", "2026-10-28", "B", db_path=self.db)
        orders = get_orders("2026-10-28", db_path=self.db)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["dish"], "B")

    def test_count_orders(self):
        save_order("T1", "2026-10-28", "A", db_path=self.db)
        save_order("T2", "2026-10-28", "B", db_path=self.db)
        c = count_orders("2026-10-28", db_path=self.db)
        self.assertEqual(c["A"], 1)
        self.assertEqual(c["B"], 1)
        self.assertEqual(c["total"], 2)

    def test_empty_db(self):
        c = count_orders("2026-10-28", db_path=self.db)
        self.assertEqual(c["total"], 0)

    def test_persistence(self):
        save_order("T1", "2026-10-28", "A", db_path=self.db)
        # reopen by calling get_orders again
        orders = get_orders("2026-10-28", db_path=self.db)
        self.assertEqual(len(orders), 1)

    def test_dish_costs(self):
        save_dish_cost("Понедельник", "A", 120, db_path=self.db)
        save_dish_cost("Понедельник", "B", None, db_path=self.db)
        costs = get_dish_costs(db_path=self.db)
        self.assertEqual(costs[("Понедельник", "A")], 120)
        self.assertIsNone(costs[("Понедельник", "B")])

    def test_reset(self):
        save_order("T1", "2026-10-28", "A", db_path=self.db)
        reset_demo_data(db_path=self.db)
        self.assertEqual(len(get_orders(db_path=self.db)), 0)

    def test_invalid_dish(self):
        with self.assertRaises(ValueError):
            save_order("T1", "2026-10-28", "C", db_path=self.db)


if __name__ == "__main__":
    unittest.main()
