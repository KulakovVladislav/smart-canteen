# -*- coding: utf-8 -*-
"""Streamlit web prototype for Smart Canteen."""

import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

from src.economics import waste_report
from src.menu import (
    COST_CEILING,
    DAY_NAMES,
    MENU,
    day_for_date,
    get_menu,
    is_vegetarian_dish,
    vegetarian_letters_for_day,
    validate_menu,
)
from src.preorder import kitchen_summary
from src.storage import (
    get_dish_costs,
    init_db,
    count_orders,
    get_orders,
    reset_demo_data,
    save_dish_cost,
    save_order,
    seed_demo_orders,
)

st.set_page_config(page_title="Умная столовая", page_icon="🍽️", layout="wide")

init_db()

STUDENT_CODE_RE = re.compile(r"^[A-Za-z0-9-]{3,20}$")


def status_for_budget(report):
    if report["has_over_limit"]:
        return "ПРЕВЫШЕНИЕ ЛИМИТА"
    if report["has_unknown"]:
        return "НЕДОСТАТОЧНО ДАННЫХ"
    return "OK"


def fmt_money(x):
    return f"{x:,.0f}".replace(",", " ")


def page_home():
    st.title("Умная столовая")
    st.caption("Демонстрационный прототип: меню по жалобам, предзаказ и расчёт экономии.")

    col1, col2, col3, col4 = st.columns(4)
    all_orders = get_orders()
    col1.metric("Заказов в базе", len(all_orders))
    report = waste_report()
    col2.metric("Потери за неделю, сом", fmt_money(report["week_total"]))
    col3.metric("Потери за год, сом", fmt_money(report["year_waste"]))
    col4.metric("Потолок себестоимости, сом", COST_CEILING)

    st.subheader("Меню на демонстрационную неделю")
    st.dataframe(
        [
            {
                "День": m["day"],
                "Блюдо A": m["dish_a"],
                "Блюдо B": m["dish_b"],
                "Жалоба": m["complaint_cluster"],
            }
            for m in get_menu()
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Сценарии экономии (расчётные)")
    for s in report["scenarios"]:
        st.write(
            f"- до {s['target']}% отходов: экономия в неделю {fmt_money(s['saving_week'])} сом, "
            f"за год {fmt_money(s['saving_year'])} сом"
        )
    st.info(
        "Потенциальная экономия — расчётный сценарий, а не подтверждённый результат. "
        "Используются только тестовые данные."
    )

    st.subheader("Статусы системы")
    st.success("CLI доступен: python app.py all")
    st.success("База данных SQLite инициализирована")
    st.warning("Реальные персональные данные не собираются; полноценная авторизация — следующий этап.")


def page_menu():
    st.title("Меню на 5 дней")
    costs = get_dish_costs()
    rows = []
    for m in get_menu():
        for letter in ("A", "B"):
            dish_name = m["dish_a"] if letter == "A" else m["dish_b"]
            veg = is_vegetarian_dish(m["day"], letter)
            cost = costs.get((m["day"], letter))
            rows.append(
                {
                    "День": m["day"],
                    "Блюдо": f"{letter} — {dish_name}",
                    "Вегетарианское": "Да" if veg else "Нет",
                    "Жалоба": m["complaint_cluster"],
                    "Стоимость, сом": "не указано" if cost is None else cost,
                }
            )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    ok, errors = validate_menu()
    if ok:
        st.success("Структура меню корректна: 5 дней, по 2 блюда, одно из них без мяса.")
    else:
        st.error("; ".join(errors))


def page_preorder():
    st.title("Предзаказ")
    st.caption("Только тестовые коды, например TEST-001. Реальные персональные данные не собираются.")

    meal_date = st.date_input("Дата питания", value=date.today())
    day_name = day_for_date(meal_date)
    if day_name:
        menu_day = next(m for m in get_menu() if m["day"] == day_name)
        dish_labels = {
            "A": menu_day["dish_a"],
            "B": menu_day["dish_b"],
        }
        st.write(f"День недели: **{day_name}**")
    else:
        dish_labels = {"A": "Блюдо A", "B": "Блюдо B"}
        st.warning("Выбран выходной день. Меню для будней; заказ всё равно можно сохранить.")

    student_code = st.text_input("Демонстрационный код ученика", value="TEST-001")
    dish = st.radio(
        "Выберите блюдо",
        options=["A", "B"],
        format_func=lambda x: f"{x} — {dish_labels[x]}",
        horizontal=True,
    )

    if st.button("Сохранить заказ"):
        if not STUDENT_CODE_RE.match(student_code.strip()):
            st.error("Код должен содержать 3-20 символов: буквы, цифры или дефис.")
        else:
            try:
                save_order(student_code.strip(), meal_date.isoformat(), dish)
                st.success("Заказ сохранён. Повторный выбор того же кода на эту дату обновит заказ, а не создаст дубликат.")
            except ValueError as exc:
                st.error(str(exc))

    existing = [o for o in get_orders(meal_date.isoformat()) if o["student_code"] == student_code.strip()]
    if existing:
        st.info(f"Текущий заказ на {meal_date.isoformat()}: блюдо {existing[0]['dish']}.")


def page_kitchen():
    st.title("Сводка для повара")
    meal_date = st.date_input("Дата сводки", value=date.today(), key="kitchen_date")
    expected = st.number_input("Ожидаемое число обедающих", min_value=0, value=500, step=10)
    date_str = meal_date.isoformat()
    counts = count_orders(date_str)
    day_name = day_for_date(meal_date)
    veg_letters = vegetarian_letters_for_day(day_name) if day_name else []
    summary = kitchen_summary(counts["orders"], expected, veg_letters)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Заказов A", summary["a_orders"])
    c2.metric("Заказов B", summary["b_orders"])
    c3.metric("Вегетарианских", summary["vegetarian_orders"])
    c4.metric("Не ответили", summary["unanswered"])

    c5, c6, c7 = st.columns(3)
    c5.metric("Базовые порции", summary["base_portions"])
    c6.metric("Резерв 5%", summary["buffer"])
    c7.metric("Итого порций", summary["total_portions"])

    st.write(
        f"Распределение по заказам: A — {summary['a_orders']}, B — {summary['b_orders']}. "
        f"Неответившие ({summary['unanswered']}) не распределяются по блюдам случайно; "
        "их доля требует исторических данных."
    )
    if summary["unanswered"] > 0:
        st.warning(
            "Исторические доли выбора неизвестны: показано общее количество необходимых порций "
            "отдельно от распределения A/B."
        )
    if expected == 0:
        st.warning("Укажите ожидаемое число обедающих, иначе расчёт неполный.")

    with st.expander("Тестовые данные"):
        if st.button("Загрузить тестовые заказы на выбранную дату"):
            seed_demo_orders(date_str)
            st.success("Тестовые заказы добавлены.")
            st.rerun()
        if st.button("Сбросить демонстрационные данные (заказы и цены)"):
            reset_demo_data()
            st.success("Демонстрационные данные очищены.")
            st.rerun()


def page_economics():
    st.title("Экономика")
    report = waste_report()
    st.subheader("Потери по дням")
    st.dataframe(
        [
            {
                "День": r["day"],
                "Отходы, %": r["pct"],
                "Потери, сом": fmt_money(r["loss"]),
            }
            for r in report["rows"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Неделя, сом", fmt_money(report["week_total"]))
    c2.metric("Год (35 недель), сом", fmt_money(report["year_waste"]))
    c3.metric("Утилизация за год, сом", fmt_money(report["util_year"]))
    c4.metric("Итого прямые потери, сом", fmt_money(report["total"]))

    st.subheader("Сценарии снижения отходов")
    st.dataframe(
        [
            {
                "Цель по отходам": f"до {s['target']}%",
                "Экономия в неделю, сом": fmt_money(s["saving_week"]),
                "Экономия за год, сом": fmt_money(s["saving_year"]),
            }
            for s in report["scenarios"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.info(
        "Сценарии — модельные оценки. Потенциальная экономия не является подтверждённым результатом."
    )


def page_budget():
    st.title("Проверка бюджета")
    st.caption(f"Лимит себестоимости: {COST_CEILING} сом на порцию.")

    costs = get_dish_costs()
    # Build a simple editable table
    st.subheader("Стоимость блюд (демонстрационный ввод)")
    edited = {}
    for m in get_menu():
        for letter in ("A", "B"):
            key = (m["day"], letter)
            current = costs.get(key)
            col1, col2, col3 = st.columns([2, 3, 2])
            with col1:
                st.write(f"{m['day']} — {letter}")
            with col2:
                val = st.number_input(
                    f"Стоимость {m['day']} {letter}",
                    min_value=0.0,
                    value=float(current) if current is not None else 0.0,
                    step=1.0,
                    key=f"cost_{m['day']}_{letter}",
                    label_visibility="collapsed",
                )
            with col3:
                known = st.checkbox(
                    "известна",
                    value=current is not None,
                    key=f"known_{m['day']}_{letter}",
                )
            edited[key] = (val, known)

    if st.button("Сохранить стоимости"):
        for (day, letter), (val, known) in edited.items():
            save_dish_cost(day, letter, val if known else None)
        st.success("Стоимости сохранены локально.")
        st.rerun()

    # Build costs dict for validator
    cost_dict = {}
    for m in get_menu():
        cost_dict[m["day"]] = {
            "A": costs.get((m["day"], "A")),
            "B": costs.get((m["day"], "B")),
        }
    # Use saved costs (re-read)
    saved = get_dish_costs()
    cost_dict = {}
    for m in get_menu():
        cost_dict[m["day"]] = {
            "A": saved.get((m["day"], "A")),
            "B": saved.get((m["day"], "B")),
        }

    from src.menu import check_budget

    report = check_budget(cost_dict)
    st.subheader("Результат проверки")
    st.write(f"Статус: **{status_for_budget(report)}**")
    st.dataframe(
        [
            {
                "День": it["day"],
                "Блюдо": it["dish"],
                "Стоимость": it["cost_display"],
                "Статус": it["status"],
            }
            for it in report["items"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    if report["has_over_limit"]:
        st.error("Есть превышение лимита себестоимости.")
    elif report["has_unknown"]:
        st.warning("Не все цены известны: статус «НЕДОСТАТОЧНО ДАННЫХ».")
    else:
        st.success("Все цены известны и не превышают лимит.")


def main():
    page = st.sidebar.radio(
        "Раздел",
        ["Главная", "Меню", "Предзаказ", "Сводка для повара", "Экономика", "Проверка бюджета"],
    )
    if page == "Главная":
        page_home()
    elif page == "Меню":
        page_menu()
    elif page == "Предзаказ":
        page_preorder()
    elif page == "Сводка для повара":
        page_kitchen()
    elif page == "Экономика":
        page_economics()
    else:
        page_budget()


if __name__ == "__main__":
    main()
