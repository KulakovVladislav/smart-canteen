# -*- coding: utf-8 -*-
"""Веб-приложение Streamlit для «Умной столовой»."""

import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

from src.ai_menu import (
    build_context,
    demo_template_menu,
    generate_menu,
    get_ai_config,
    is_configured,
    validate_ai_menu,
)
from src.economics import waste_report
from src.menu import (
    COST_CEILING,
    DAY_NAMES,
    get_active_menu,
    get_menu,
    day_for_date,
    is_vegetarian_dish,
    validate_menu,
    vegetarian_letters_for_day,
)
from src.preorder import kitchen_summary
from src.storage import (
    count_orders,
    get_dish_costs,
    get_leftovers,
    get_orders,
    get_saved_menu,
    init_db,
    reset_demo_data,
    save_dish_cost,
    save_leftover,
    save_menu,
    save_order,
    seed_demo_orders,
)

st.set_page_config(page_title="Умная столовая", page_icon="🍽️", layout="wide")

init_db()

STUDENT_CODE_RE = re.compile(r"^[A-Za-z0-9-]{3,20}$")

CUSTOM_CSS = """
<style>
:root {
    /* Фон и поверхности */
    --sc-bg: #f4f5f3;
    --sc-bg-soft: #eceee8;
    --sc-card: #ffffff;
    --sc-surface: #f7f8f5;
    /* Текст */
    --sc-text: #1b2a26;
    --sc-text-soft: #4a5c55;
    --sc-muted: #7a8a82;
    /* Акцент и состояния */
    --sc-primary: #0f5b4f;
    --sc-primary-soft: #e8f4f1;
    --sc-success: #1f8a5a;
    --sc-warning: #b8862b;
    --sc-danger: #b33a2b;
    /* Границы и разделители */
    --sc-border: #e3e5e1;
    --sc-divider: #e9ebde;
    /* Тени */
    --sc-shadow-sm: 0 1px 2px rgba(27, 42, 38, 0.06);
    --sc-shadow-md: 0 4px 12px rgba(27, 42, 38, 0.08);
    /* Радиусы */
    --sc-radius-sm: 8px;
    --sc-radius: 12px;
    --sc-radius-lg: 16px;
    /* Типографика */
    --sc-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --sc-heading-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --sc-text-base: 0.95rem;
    --sc-text-sm: 0.85rem;
    --sc-text-xs: 0.78rem;
    --sc-line-height: 1.5;
    /* Отступы */
    --sc-space-xs: 4px;
    --sc-space-sm: 8px;
    --sc-space: 12px;
    --sc-space-md: 16px;
    --sc-space-lg: 24px;
    --sc-space-xl: 32px;
}

/* Тёмная тема — активируется Streamlit через data-theme="dark" */
html[data-theme="dark"] {
    --sc-bg: #0f1412;
    --sc-bg-soft: #161b18;
    --sc-card: #181e1b;
    --sc-surface: #1c2320;
    --sc-text: #e8efe9;
    --sc-text-soft: #b9c6be;
    --sc-muted: #8a9890;
    --sc-primary: #1fb08a;
    --sc-primary-soft: #143830;
    --sc-success: #2fb978;
    --sc-warning: #e0a84b;
    --sc-danger: #e06a5a;
    --sc-border: #2a312d;
    --sc-divider: #232926;
    --sc-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --sc-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.5);
}

.stApp { background: var(--sc-bg); color: var(--sc-text); }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1200px; }
h1, h2, h3, h4 { color: var(--sc-text); font-family: var(--sc-heading-font); letter-spacing: -0.01em; }
p, li, span { color: var(--sc-text-soft); }
.sc-muted { color: var(--sc-muted); font-size: var(--sc-text-sm); }
.sc-card {
    background: var(--sc-card);
    border: 1px solid var(--sc-border);
    border-radius: var(--sc-radius);
    padding: var(--sc-space-md);
    margin-bottom: var(--sc-space-md);
    box-shadow: var(--sc-shadow-sm);
}
.sc-status-ok { color: var(--sc-success); font-weight: 600; }
.sc-status-warn { color: var(--sc-warning); font-weight: 600; }
.sc-status-bad { color: var(--sc-danger); font-weight: 600; }
div[data-testid="stMetric"] {
    background: var(--sc-card);
    border: 1px solid var(--sc-border);
    border-radius: var(--sc-radius);
    padding: 0.75rem 1rem;
}
div[data-testid="stMetricLabel"] { color: var(--sc-muted); }
div[data-testid="stMetricValue"] { color: var(--sc-text); }
div[data-testid="stDataFrame"] { border-radius: var(--sc-radius); overflow: hidden; }
div[data-testid="stDataFrame"] th {
    background: var(--sc-surface);
    color: var(--sc-text);
    border-bottom: 1px solid var(--sc-divider);
}
div[data-testid="stDataFrame"] td { border-bottom: 1px solid var(--sc-divider); }

/* Кнопки */
.stButton > button {
    border-radius: var(--sc-radius);
    border: 1px solid var(--sc-border);
    background: var(--sc-card);
    color: var(--sc-text);
    transition: background 0.15s ease, border-color 0.15s ease;
}
.stButton > button:hover {
    background: var(--sc-surface);
    border-color: var(--sc-primary);
}
.stButton > button:disabled { opacity: 0.5; }

/* Фокус */
:focus-visible {
    outline: 2px solid var(--sc-primary);
    outline-offset: 2px;
}

/* Сайдбар */
[data-testid="stSidebar"] { background: var(--sc-bg-soft); border-right: 1px solid var(--sc-divider); }

/* Информационные блоки */
.stAlert { border-radius: var(--sc-radius); }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def fmt_money(x):
    return f"{x:,.0f}".replace(",", " ")


def status_for_budget(report):
    if report["has_over_limit"]:
        return "ПРЕВЫШЕНИЕ ЛИМИТА"
    if report["has_unknown"]:
        return "НЕДОСТАТОЧНО ДАННЫХ"
    return "OK"


def page_home():
    st.title("Умная столовая")
    st.caption("Цикл: жалобы → AI-меню → предзаказ → сводка кухни → отходы → эффект. Тестовые данные и расчётные сценарии явно отделены от измерений.")

    all_orders = get_orders()
    try:
        report = waste_report()
    except (OSError, ValueError) as exc:
        report = None
        st.warning(f"Данные об отходах недоступны: {exc}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Заказов в базе", len(all_orders))
    col2.metric("Потери за неделю, сом", "нет данных" if report is None else fmt_money(report["week_total"]))
    col3.metric("Потери за год, сом", "нет данных" if report is None else fmt_money(report["year_waste"]))
    col4.metric("Потолок себестоимости, сом", COST_CEILING)

    st.markdown('<div class="sc-card">', unsafe_allow_html=True)
    st.subheader("Меню на текущую неделю")
    menu = get_active_menu()
    st.dataframe(
        [
            {
                "День": m["day"],
                "Блюдо A": m["dish_a"],
                "Блюдо B": m["dish_b"],
                "Вегетарианское": ("A" if m.get("dish_a_vegetarian") else "") + (" / B" if m.get("dish_b_vegetarian") else ""),
                "Жалоба": m["complaint_cluster"],
            }
            for m in menu
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if report is not None:
        st.markdown('<div class="sc-card">', unsafe_allow_html=True)
        st.subheader("Сценарии экономии (расчётные)")
        for s in report["scenarios"]:
            st.write(
                f"- до {s['target']}% отходов: экономия в неделю {fmt_money(s['saving_week'])} сом, "
                f"за год {fmt_money(s['saving_year'])} сом"
            )
        st.info(
            "Потенциальная экономия — расчётный сценарий, а не подтверждённый результат. "
            "Используются только тестовые данные. Демонстрационные данные явно отделены от измерений."
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sc-card">', unsafe_allow_html=True)
    st.subheader("Статусы системы")
    st.success("CLI доступен: python app.py all (через python3 .venv)")
    st.success("База данных SQLite инициализирована")
    saved = get_saved_menu()
    if saved:
        st.info("Используется сохранённое меню (в том числе после AI-генерации).")
    else:
        st.info("Используется встроенное демонстрационное меню.")
    st.warning("Реальные персональные данные не собираются; полноценная авторизация — следующий этап.")
    st.markdown("</div>", unsafe_allow_html=True)


def page_menu():
    st.title("Меню на 5 дней")
    menu = get_active_menu()
    costs = get_dish_costs()
    rows = []
    for m in menu:
        for letter in ("A", "B"):
            dish_name = m["dish_a"] if letter == "A" else m["dish_b"]
            veg = m.get("dish_a_vegetarian") if letter == "A" else m.get("dish_b_vegetarian")
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
    ok, errors = validate_menu(menu)
    if ok:
        st.success("Структура меню корректна: 5 дней, по 2 блюда, есть вегетарианский вариант.")
    else:
        st.error("; ".join(errors))


def page_preorder():
    st.title("Предзаказ")
    st.caption("Только тестовые коды, например TEST-001. Реальные персональные данные не собираются.")

    meal_date = st.date_input("Дата питания", value=date.today())
    day_name = day_for_date(meal_date)
    if day_name:
        menu_day = next((m for m in get_active_menu() if m["day"] == day_name), None)
        dish_labels = {
            "A": menu_day["dish_a"] if menu_day else "Блюдо A",
            "B": menu_day["dish_b"] if menu_day else "Блюдо B",
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
    hist_mode = st.selectbox(
        "Распределение неответивших",
        ["Неизвестно (не распределять)", "Оценка: все A", "Оценка: все B", "Оценка: поровну"],
        index=0,
    )
    hist_map = {
        "Неизвестно (не распределять)": None,
        "Оценка: все A": "A",
        "Оценка: все B": "B",
        "Оценка: поровну": "split",
    }
    historical = hist_map[hist_mode]

    date_str = meal_date.isoformat()
    counts = count_orders(date_str)
    day_name = day_for_date(meal_date)
    veg_letters = vegetarian_letters_for_day(day_name, menu=get_active_menu()) if day_name else []
    summary = kitchen_summary(counts["orders"], expected, veg_letters, historical_shares=None, default_choice=historical)

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
        "Неответившие не распределяются по блюдам автоматически."
    )
    if summary["unknown_distribution"] > 0:
        st.warning(
            f"Исторические доли неизвестны: показано общее количество необходимых порций "
            f"({summary['unknown_distribution']} неответивших) отдельно от распределения A/B."
        )
    if historical:
        st.info("Оценочное распределение неответивших включено в порции A/B как допущение, а не измерение.")
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


def page_leftovers():
    st.title("Фактические остатки")
    st.caption("Ручной ввод после обеда. Эти записи — измерения, внесённые вручную, а не автоматические.")

    with st.form("leftover_form"):
        record_date = st.date_input("Дата", value=date.today())
        waste_mass = st.number_input("Масса пищевых отходов, кг", min_value=0.0, step=0.5)
        leftover_portions = st.number_input("Оставшихся порций", min_value=0, step=1)
        note = st.text_input("Примечание")
        submitted = st.form_submit_button("Сохранить остатки")
    if submitted:
        try:
            save_leftover(record_date.isoformat(), waste_mass, int(leftover_portions), note)
            st.success("Запись сохранена.")
        except (ValueError, TypeError) as exc:
            st.error(str(exc))

    records = get_leftovers()
    st.subheader("История измерений")
    if records:
        st.dataframe(
            [
                {
                    "Дата": r["record_date"],
                    "Отходы, кг": r["waste_mass_kg"],
                    "Порций осталось": r["leftover_portions"],
                    "Примечание": r["note"] or "",
                }
                for r in records
            ],
            use_container_width=True,
            hide_index=True,
        )
        masses = [r["waste_mass_kg"] for r in records if r["waste_mass_kg"] is not None]
        if masses:
            avg = sum(masses) / len(masses)
            st.metric("Средняя масса отходов по записям, кг", f"{avg:.1f}")
            st.caption("Базовая оценка кейса — около 60 кг/день. Сравнение возможно только при достаточном числе записей.")
    else:
        st.info("Записей пока нет. Внесите первый результат после обеда.")


def page_economics():
    st.title("Экономика")
    try:
        report = waste_report()
    except (OSError, ValueError) as exc:
        st.error(f"Не удалось загрузить данные об отходах: {exc}")
        return
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
    c2.metric("Год, продукты, сом", fmt_money(report["year_waste"]))
    c3.metric("Утилизация за год, сом", fmt_money(report["util_year"]))
    c4.metric("Сумма категорий, сом", fmt_money(report["combined_losses"]))

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
    st.info("Сценарии — модельные оценки. Потенциальная экономия не является подтверждённым результатом.")

    with st.expander("Исходные допущения"):
        st.markdown(
            "- Процент отходов применяется к дневному бюджету закупок 70 000 сом (упрощённое допущение).\n"
            "- Стоимость потерянных продуктов и утилизация показаны отдельно; автоматическое сложение может привести к двойному учёту.\n"
            "- Реальная себестоимость блюд неизвестна; лимит 140 сом/порция проверяется по введённым ценам."
        )


def page_budget():
    st.title("Проверка бюджета")
    st.caption(f"Лимит себестоимости: {COST_CEILING} сом на порцию.")

    costs = get_dish_costs()
    st.subheader("Стоимость блюд (демонстрационный ввод)")
    edited = {}
    for m in get_active_menu():
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
        try:
            for (day, letter), (val, known) in edited.items():
                save_dish_cost(day, letter, val if known else None)
            st.success("Стоимости сохранены локально.")
            st.rerun()
        except (ValueError, TypeError) as exc:
            st.error(str(exc))

    saved = get_dish_costs()
    cost_dict = {}
    for m in get_active_menu():
        cost_dict[m["day"]] = {
            "A": saved.get((m["day"], "A")),
            "B": saved.get((m["day"], "B")),
        }

    from src.menu import check_budget

    report = check_budget(cost_dict)
    st.subheader("Результат проверки")
    status = status_for_budget(report)
    icon = {"OK": "✅", "ПРЕВЫШЕНИЕ ЛИМИТА": "⛔", "НЕДОСТАТОЧНО ДАННЫХ": "⚠️"}.get(status, "")
    st.write(f"Статус: **{icon} {status}**")
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


def page_ai():
    st.title("AI-меню")
    config = get_ai_config()
    if config["configured"]:
        st.success(f"Провайдер настроен: {config['provider']} / {config['model']}")
    else:
        st.warning("AI-провайдер не настроен. Задайте AI_API_KEY (или OPENAI_API_KEY). Приложение продолжает работать на сохранённом меню.")

    col1, col2 = st.columns(2)
    generate_clicked = col1.button("Сформировать предложение меню")
    template_clicked = col2.button("Показать демонстрационный шаблон (не AI)")

    result = st.session_state.get("ai_result")
    if generate_clicked:
        if not config["configured"]:
            st.error("Провайдер не настроен: генерация недоступна.")
        else:
            try:
                with st.spinner("Обращение к языковой модели..."):
                    ctx = build_context(get_active_menu())
                    result = generate_menu(ctx)
                st.session_state["ai_result"] = result
                st.success("Предложение получено от языковой модели.")
            except Exception as exc:
                st.error(f"Ошибка генерации: {exc}")
                result = None
                st.session_state.pop("ai_result", None)

    if template_clicked:
        result = demo_template_menu()
        st.session_state["ai_result"] = result
        st.info("Показан демонстрационный шаблон. Это не результат обращения к языковой модели.")

    result = st.session_state.get("ai_result")
    if result:
        st.subheader("Предпросмотр меню")
        st.caption(f"Источник: {result['source']} (provider={result.get('provider')}, model={result.get('model')})")
        st.dataframe(
            [
                {
                    "День": m["day"],
                    "Блюдо A": m["dish_a"],
                    "Блюдо B": m["dish_b"],
                    "Вегетарианское": ("A" if m.get("dish_a_vegetarian") else "") + (" / B" if m.get("dish_b_vegetarian") else ""),
                    "Жалоба": m["complaint_cluster"],
                }
                for m in result["menu"]
            ],
            use_container_width=True,
            hide_index=True,
        )
        ok, errors = validate_ai_menu(result["menu"])
        if ok:
            st.success("Структура ответа корректна.")
        else:
            st.error("; ".join(errors))

        if result["source"] == "ai" and st.button("Сохранить как текущее меню"):
            try:
                save_menu(result["menu"])
                st.success("Меню сохранено. Обновите страницу «Меню».")
            except ValueError as exc:
                st.error(str(exc))

        if result.get("raw_text"):
            with st.expander("Сырой ответ модели"):
                st.code(result["raw_text"])


def main():
    page = st.sidebar.radio(
        "Раздел",
        ["Главная", "Меню", "Предзаказ", "Кухня", "Отходы", "Экономика", "Проверка бюджета", "AI-меню"],
    )
    if page == "Главная":
        page_home()
    elif page == "Меню":
        page_menu()
    elif page == "Предзаказ":
        page_preorder()
    elif page == "Кухня":
        page_kitchen()
    elif page == "Отходы":
        page_leftovers()
    elif page == "Экономика":
        page_economics()
    elif page == "Проверка бюджета":
        page_budget()
    else:
        page_ai()


if __name__ == "__main__":
    main()
