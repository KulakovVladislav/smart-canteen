import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.storage import get_leftovers, init_db, reset_demo_data, save_leftover


class TestLeftovers(unittest.TestCase):
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

    def test_save_and_get(self):
        save_leftover("2026-10-28", 12.5, 3, "note", db_path=self.db)
        rows = get_leftovers(db_path=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_date"], "2026-10-28")
        self.assertEqual(rows[0]["waste_mass_kg"], 12.5)
        self.assertEqual(rows[0]["leftover_portions"], 3)

    def test_invalid_mass(self):
        with self.assertRaises(ValueError):
            save_leftover("2026-10-28", -1, db_path=self.db)

    def test_reset_removes_leftovers(self):
        save_leftover("2026-10-28", 1, db_path=self.db)
        reset_demo_data(db_path=self.db)
        self.assertEqual(len(get_leftovers(db_path=self.db)), 0)


if __name__ == "__main__":
    unittest.main()
