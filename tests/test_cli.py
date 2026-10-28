import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app


class TestCLI(unittest.TestCase):
    def _run(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = app.main(["app.py", *args])
        return code, buf.getvalue()

    def test_all(self):
        code, out = self._run("all")
        self.assertEqual(code, 0)
        self.assertIn("МЕНЮ НА 5 ДНЕЙ", out)
        self.assertIn("Итого порций к приготовлению", out)

    def test_menu(self):
        code, out = self._run("menu")
        self.assertEqual(code, 0)
        self.assertIn("Понедельник", out)

    def test_preorder(self):
        code, out = self._run("preorder")
        self.assertEqual(code, 0)
        self.assertIn("Порций блюда A:", out)

    def test_budget_check(self):
        code, out = self._run("budget-check")
        self.assertEqual(code, 0)
        self.assertIn("Потолок себестоимости", out)

    def test_unknown_command(self):
        code, out = self._run("nope")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
