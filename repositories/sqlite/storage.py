# -*- coding: utf-8 -*-
"""Хранение заказов и стоимостей блюд в SQLite (только стандартная библиотека)."""

from __future__ import annotations

import os
import sqlite3
from datetime import date

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "smart_canteen.db",
)


def get_db_path(db_path=None):
    return db_path or DEFAULT_DB_PATH


def get_connection(db_path=None):
    path = get_db_path(db_path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(db_path=None):
    path = get_db_path(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders
            (
                id
                INTEGER
                PRIMARY
                KEY
                AUTOINCREMENT,
                student_code
                TEXT
                NOT
                NULL,
                meal_date
                TEXT
                NOT
                NULL,
                dish
                TEXT
                NOT
                NULL,
                created_at
                TEXT
                NOT
                NULL,
                updated_at
                TEXT
                NOT
                NULL,
                UNIQUE
            (
                student_code,
                meal_date
            )
                )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dish_costs
            (
                day
                TEXT
                NOT
                NULL,
                dish
                TEXT
                NOT
                NULL,
                cost
                REAL,
                updated_at
                TEXT
                NOT
                NULL,
                PRIMARY
                KEY
            (
                day,
                dish
            )
                )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leftovers
            (
                id
                INTEGER
                PRIMARY
                KEY
                AUTOINCREMENT,
                record_date
                TEXT
                NOT
                NULL,
                waste_mass_kg
                REAL,
                leftover_portions
                INTEGER,
                note
                TEXT,
                created_at
                TEXT
                NOT
                NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_items
            (
                day
                TEXT
                PRIMARY
                KEY,
                dish_a
                TEXT
                NOT
                NULL,
                dish_b
                TEXT
                NOT
                NULL,
                complaint_cluster
                TEXT,
                dish_a_vegetarian
                INTEGER
                NOT
                NULL
                DEFAULT
                0,
                dish_b_vegetarian
                INTEGER
                NOT
                NULL
                DEFAULT
                0,
                updated_at
                TEXT
                NOT
                NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_meal_date ON orders(meal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leftovers_record_date ON leftovers(record_date)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_subscribers
            (
                chat_id
                TEXT
                PRIMARY
                KEY,
                created_at
                TEXT
                NOT
                NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_jobs
            (
                job_name TEXT NOT NULL,
                run_date TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (job_name, run_date)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return date.today().isoformat()


def _now():
    from datetime import date

    return date.today().isoformat()


def save_order(student_code, meal_date, dish, db_path=None):
    student_code = str(student_code).strip()
    meal_date = str(meal_date).strip()
    dish = str(dish).strip().upper()
    if dish not in ("A", "B"):
        raise ValueError("dish must be A or B")
    if not student_code:
        raise ValueError("student_code is required")
    try:
        meal_date = date.fromisoformat(meal_date).isoformat()
    except ValueError as exc:
        raise ValueError("meal_date must use YYYY-MM-DD") from exc

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        now = _now()
        conn.execute(
            """
            INSERT INTO orders (student_code, meal_date, dish, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(student_code, meal_date) DO
            UPDATE SET
                dish = excluded.dish,
                updated_at = excluded.updated_at
            """,
            (student_code, meal_date, dish, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_order(student_code, meal_date, db_path=None):
    student_code = str(student_code).strip()
    meal_date = str(meal_date).strip()
    if not student_code or not meal_date:
        raise ValueError("student_code and meal_date are required")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM orders WHERE student_code = ? AND meal_date = ?",
            (student_code, meal_date),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def cancel_order(student_code, meal_date, db_path=None):
    return delete_order(student_code, meal_date, db_path=db_path)


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
            try:
                value = float(cost)
            except (TypeError, ValueError) as exc:
                raise ValueError("cost must be a number") from exc
            if value < 0:
                raise ValueError("cost must be non-negative")
        conn.execute(
            """
            INSERT INTO dish_costs (day, dish, cost, updated_at)
            VALUES (?, ?, ?, ?) ON CONFLICT(day, dish) DO
            UPDATE SET
                cost = excluded.cost,
                updated_at = excluded.updated_at
            """,
            (day, dish, value, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def save_dish_costs(costs, db_path=None):
    """Save a full cost sheet atomically.

    ``costs`` maps ``(day, dish)`` to a number or ``None`` for an unknown
    value. A validation error leaves the previous sheet untouched.
    """
    normalized = []
    for key, cost in dict(costs).items():
        try:
            day, dish = key
        except (TypeError, ValueError) as exc:
            raise ValueError("cost keys must be (day, dish) pairs") from exc
        day = str(day).strip()
        dish = str(dish).strip().upper()
        if not day or dish not in ("A", "B"):
            raise ValueError("each cost requires a day and dish A or B")
        if cost is None or cost == "":
            value = None
        else:
            try:
                value = float(cost)
            except (TypeError, ValueError) as exc:
                raise ValueError("cost must be a number") from exc
            if value < 0:
                raise ValueError("cost must be non-negative")
        normalized.append((day, dish, value, _now()))

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO dish_costs (day, dish, cost, updated_at)
            VALUES (?, ?, ?, ?) ON CONFLICT(day, dish) DO
            UPDATE SET cost = excluded.cost, updated_at = excluded.updated_at
            """,
            normalized,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
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


def save_leftover(record_date, waste_mass_kg=None, leftover_portions=None, note="", db_path=None):
    record_date = str(record_date).strip()
    if not record_date:
        raise ValueError("record_date is required")
    mass = None
    if waste_mass_kg not in (None, ""):
        try:
            mass = float(waste_mass_kg)
        except (TypeError, ValueError) as exc:
            raise ValueError("waste_mass_kg must be a number") from exc
        if mass < 0:
            raise ValueError("waste_mass_kg must be non-negative")
    portions = None
    if leftover_portions not in (None, ""):
        if isinstance(leftover_portions, bool):
            raise ValueError("leftover_portions must be an integer")
        try:
            if isinstance(leftover_portions, float):
                if not leftover_portions.is_integer():
                    raise ValueError("leftover_portions must be an integer")
            portions = int(leftover_portions)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("leftover_portions must be an integer") from exc
        if portions < 0:
            raise ValueError("leftover_portions must be non-negative")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO leftovers (record_date, waste_mass_kg, leftover_portions, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (record_date, mass, portions, str(note or "").strip(), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_leftovers(db_path=None, limit=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        sql = "SELECT id, record_date, waste_mass_kg, leftover_portions, note, created_at FROM leftovers ORDER BY record_date DESC, id DESC"
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, (int, float, str)):
                raise ValueError("limit must be an integer")
            try:
                if isinstance(limit, float) and not limit.is_integer():
                    raise ValueError("limit must be an integer")
                limit = int(limit)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("limit must be an integer") from exc
            if limit < 0:
                raise ValueError("limit must be non-negative")
            sql += " LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


from domain.menu import MENU, _strict_bool, validate_menu


def save_menu(menu, db_path=None):
    ok, errors = validate_menu(menu)
    if not ok:
        raise ValueError("; ".join(errors))
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        old = {
            row["day"]: (row["dish_a"], row["dish_b"])
            for row in conn.execute("SELECT day, dish_a, dish_b FROM menu_items")
        }
        changed_days = [
            str(item["day"]).strip()
            for item in menu
            if old.get(str(item["day"]).strip())
            != (str(item["dish_a"]).strip(), str(item["dish_b"]).strip())
        ]
        if changed_days:
            conn.executemany("DELETE FROM dish_costs WHERE day = ?", [(day,) for day in changed_days])
        conn.execute("DELETE FROM menu_items")
        for item in menu:
            conn.execute(
                """
                INSERT INTO menu_items (day, dish_a, dish_b, complaint_cluster, dish_a_vegetarian, dish_b_vegetarian,
                                        updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item["day"]).strip(),
                    str(item["dish_a"]).strip(),
                    str(item["dish_b"]).strip(),
                    str(item.get("complaint_cluster", "")).strip(),
                    1 if _strict_bool(item.get("dish_a_vegetarian", False)) else 0,
                    1 if _strict_bool(item.get("dish_b_vegetarian", False)) else 0,
                    _now(),
                ),
            )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("menu contains duplicate or invalid day") from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_saved_menu(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT day, dish_a, dish_b, complaint_cluster, dish_a_vegetarian, dish_b_vegetarian FROM menu_items"
        ).fetchall()
        if not rows:
            return None
        by_day = {r["day"]: r for r in rows}
        ordered_days = [m["day"] for m in MENU]
        result = []
        for day in ordered_days:
            r = by_day.get(day)
            if r is None:
                # Восстанавливаем отсутствующий день из встроенного меню.
                fallback = next((m for m in MENU if m["day"] == day), None)
                if fallback is None:
                    continue
                result.append(
                    {
                        "day": fallback["day"],
                        "dish_a": fallback["dish_a"],
                        "dish_b": fallback["dish_b"],
                        "complaint_cluster": fallback.get("complaint_cluster", ""),
                        "cost_assumption_note": "не указано",
                        "dish_a_vegetarian": bool(fallback.get("dish_a_vegetarian", False)),
                        "dish_b_vegetarian": bool(fallback.get("dish_b_vegetarian", False)),
                    }
                )
                continue
            result.append(
                {
                    "day": r["day"],
                    "dish_a": r["dish_a"],
                    "dish_b": r["dish_b"],
                    "complaint_cluster": r["complaint_cluster"] or "",
                    "cost_assumption_note": "не указано",
                    "dish_a_vegetarian": bool(r["dish_a_vegetarian"]),
                    "dish_b_vegetarian": bool(r["dish_b_vegetarian"]),
                }
            )
        # Сохранённое меню ограничено каноническими пятью днями.
        # Дополнительные/некорректные записи не добавляются, чтобы
        # не было дублирования дней в интерфейсе.
        if not result:
            return None
        return result
    finally:
        conn.close()


def subscribe_chat(chat_id, db_path=None):
    chat_id = str(chat_id).strip()
    if not chat_id:
        raise ValueError("chat_id is required")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO telegram_subscribers (chat_id, created_at) VALUES (?, ?)",
            (chat_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def unsubscribe_chat(chat_id, db_path=None):
    chat_id = str(chat_id).strip()
    if not chat_id:
        raise ValueError("chat_id is required")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("DELETE FROM telegram_subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_subscribers(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT chat_id FROM telegram_subscribers ORDER BY chat_id").fetchall()
        return [r["chat_id"] for r in rows]
    finally:
        conn.close()


def was_scheduled_job_completed(job_name, run_date, db_path=None):
    """Return whether a scheduled job was completed on a given ISO date."""
    job_name = str(job_name or "").strip()
    try:
        normalized_date = date.fromisoformat(str(run_date).strip()).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("run_date must use YYYY-MM-DD") from exc
    if not job_name:
        raise ValueError("job_name is required")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM scheduled_jobs WHERE job_name = ? AND run_date = ?",
            (job_name, normalized_date),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_scheduled_job_completed(job_name, run_date, db_path=None):
    """Persist a successful scheduled run so a restart does not duplicate it."""
    job_name = str(job_name or "").strip()
    try:
        normalized_date = date.fromisoformat(str(run_date).strip()).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("run_date must use YYYY-MM-DD") from exc
    if not job_name:
        raise ValueError("job_name is required")
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO scheduled_jobs (job_name, run_date, completed_at) VALUES (?, ?, ?)",
            (job_name, normalized_date, _now()),
        )
        conn.commit()
    finally:
        conn.close()


_DEPRECATED_ALIASES = {
    "save_leftovers": save_leftover,
    "get_leftover_history": get_leftovers,
    "list_leftovers": get_leftovers,
}


def __getattr__(name):
    if name in _DEPRECATED_ALIASES:
        import warnings

        warnings.warn(
            f"{__name__}.{name} is deprecated; use the canonical name instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED_ALIASES[name]
    raise AttributeError(f"module '{__name__}' has no attribute {name!r}")


def reset_demo_data(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM dish_costs")
        conn.execute("DELETE FROM leftovers")
        conn.commit()
    finally:
        conn.close()


def seed_demo_orders(meal_date, db_path=None):
    samples = ["TEST-001", "TEST-002", "TEST-003", "TEST-004", "TEST-005"]
    choices = ["A", "A", "B", "B", "A"]
    for code, dish in zip(samples, choices):
        save_order(code, meal_date, dish, db_path=db_path)


def seed_presentation_data(meal_date, db_path=None):
    """Replace local demo data with one deterministic, presentation-ready dataset.

    The function is intentionally explicit: it clears only orders, dish costs and
    leftover measurements, never the saved menu or Telegram subscriber list.
    """
    try:
        target = date.fromisoformat(str(meal_date).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("meal_date must use YYYY-MM-DD") from exc

    reset_demo_data(db_path=db_path)
    choices = ("A", "B", "A", "A", "B", "A", "B", "A", "B", "A", "B", "A", "A", "B", "B", "A", "B", "A")
    for index, dish in enumerate(choices, start=1):
        save_order(f"DEMO-{index:03d}", target.isoformat(), dish, db_path=db_path)

    costs = (128, 136, 122, 130, 116, 124, 134, 120, 118, 126)
    for item, pair in zip(MENU, zip(costs[::2], costs[1::2])):
        save_dish_cost(item["day"], "A", pair[0], db_path=db_path)
        save_dish_cost(item["day"], "B", pair[1], db_path=db_path)

    for days_back, mass, portions, note in (
        (3, 58.0, 36, "До предзаказа"),
        (2, 51.5, 24, "После уточнения меню"),
        (1, 46.0, 18, "Предзаказы учтены"),
    ):
        record_date = date.fromordinal(target.toordinal() - days_back).isoformat()
        save_leftover(record_date, mass, portions, note, db_path=db_path)

    return {
        "meal_date": target.isoformat(),
        "orders": len(choices),
        "costs": len(costs),
        "leftovers": 3,
    }
