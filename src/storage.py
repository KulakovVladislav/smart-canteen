# -*- coding: utf-8 -*-
"""SQLite storage for orders and dish costs (stdlib only)."""

import os
import sqlite3
from datetime import date

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "smart_canteen.db"
)


def get_db_path(db_path=None):
    return db_path or DEFAULT_DB_PATH


def get_connection(db_path=None):
    path = get_db_path(db_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL,
                meal_date TEXT NOT NULL,
                dish TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(student_code, meal_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dish_costs (
                day TEXT NOT NULL,
                dish TEXT NOT NULL,
                cost REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (day, dish)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _now():
    return date.today().isoformat()


def save_order(student_code, meal_date, dish, db_path=None):
    student_code = str(student_code).strip()
    meal_date = str(meal_date).strip()
    dish = str(dish).strip().upper()
    if dish not in ("A", "B"):
        raise ValueError("dish must be A or B")
    if not student_code:
        raise ValueError("student_code is required")
    if not meal_date:
        raise ValueError("meal_date is required")

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        now = _now()
        conn.execute(
            """
            INSERT INTO orders (student_code, meal_date, dish, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(student_code, meal_date) DO UPDATE SET
                dish = excluded.dish,
                updated_at = excluded.updated_at
            """,
            (student_code, meal_date, dish, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_orders(meal_date=None, db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if meal_date is None:
            rows = conn.execute(
                "SELECT student_code, meal_date, dish, created_at, updated_at FROM orders ORDER BY meal_date, student_code"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT student_code, meal_date, dish, created_at, updated_at FROM orders WHERE meal_date = ? ORDER BY student_code",
                (str(meal_date).strip(),),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_orders(meal_date, db_path=None):
    orders = get_orders(meal_date, db_path=db_path)
    a = sum(1 for o in orders if o["dish"] == "A")
    b = sum(1 for o in orders if o["dish"] == "B")
    return {"A": a, "B": b, "total": len(orders), "orders": orders}


def save_dish_cost(day, dish, cost, db_path=None):
    day = str(day).strip()
    dish = str(dish).strip().upper()
    if dish not in ("A", "B"):
        raise ValueError("dish must be A or B")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if cost is None or cost == "":
            value = None
        else:
            value = float(cost)
            if value < 0:
                raise ValueError("cost must be non-negative")
        conn.execute(
            """
            INSERT INTO dish_costs (day, dish, cost, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(day, dish) DO UPDATE SET
                cost = excluded.cost,
                updated_at = excluded.updated_at
            """,
            (day, dish, value, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_dish_costs(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT day, dish, cost FROM dish_costs").fetchall()
        result = {}
        for r in rows:
            result[(r["day"], r["dish"])] = r["cost"]
        return result
    finally:
        conn.close()


def reset_demo_data(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM dish_costs")
        conn.commit()
    finally:
        conn.close()


def seed_demo_orders(meal_date, db_path=None):
    samples = ["TEST-001", "TEST-002", "TEST-003", "TEST-004", "TEST-005"]
    choices = ["A", "A", "B", "B", "A"]
    for code, dish in zip(samples, choices):
        save_order(code, meal_date, dish, db_path=db_path)
