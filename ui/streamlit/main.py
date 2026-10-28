# -*- coding: utf-8 -*-
"""Веб-приложение Streamlit для «Умной столовой»."""

import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

from services.ai_menu import (
    build_context,
    demo_template_menu,
    generate_menu,
    get_ai_config,
    validate_ai_menu,
)
from domain.economics import waste_report
from domain.menu import (
    COST_CEILING,
    check_budget,
    get_active_menu,
    day_for_date,
    validate_menu,
    vegetarian_letters_for_day,
)
from domain.preorder import kitchen_summary
from repositories.storage import (
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

STUDENT_CODE_RE = re.compile(r"^[A-Za-z0-9-]{3,20}$")

CUSTOM_CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.css")
try:
    with open(CUSTOM_CSS_PATH, encoding="utf-8") as _f:
        CUSTOM_CSS = _f.read()
except FileNotFoundError:
    CUSTOM_CSS = ""

st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)


def fmt_money(x):
    return f"{x:,.0f}".replace(",", " ")


def status_for_budget(report):
    if report["has_over_limit"]:
        return "ПРЕВЫШЕНИЕ ЛИМИТА"
    if report["has_unknown"]:
        return "НЕДОСТАТОЧНО ДАННЫХ"
    return "OK"


def _go_to_preorder():
    st.session_state["page"] = "Заказы"

def _go_to_kitchen():
    st.session_state["page"] = "Кухня"


def _reset_demo_data():
    try:
        reset_demo_data()
        st.session_state["demo_reset_flash"] = (
            "success",
            "Демонстрационные данные очищены: заказы, стоимости блюд и остатки удалены. "
            "Сохранённое меню не изменено.",
        )
    except Exception as exc:
        st.session_state["demo_reset_flash"] = (
            "error",
            f"Не удалось очистить демонстрационные данные: {exc}",
        )
    st.session_state["reset_confirmed"] = False


def page_home():
    st.title("Умная столовая")
    st.caption("Планирование меню под жалобы учеников, предзаказ, учёт остатков и расчёт экономики.")

    all_orders = get_orders()
    try:
        report = waste_report()
    except (OSError, ValueError) as exc:
        report = None
        st.warning(f"Данные об отходах недоступны: {exc}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Заказов в базе", len(all_orders))
    col2.metric("Потери за неделю, сом", "—" if report is None else fmt_money(report["week_total"]))
    col3.metric("Потери за год, сом", "—" if report is None else fmt_money(report["year_waste"]))

    st.write("")
    st.button("Открыть сводку для кухни 🍳", on_click=_go_to_kitchen, width="stretch")

    with st.container(border=True, key="home-menu-card"):
        st.subheader("Меню на текущую неделю")
        menu = get_active_menu()
        st.dataframe(
            [
                {
                    "День": m["day"],
                    "Блюдо A": m["dish_a"],
                    "Блюдо B": m["dish_b"],
                    "Вегетарианское": _veg_label(m),
                    "Жалоба": m["complaint_cluster"],
                }
                for m in menu
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "День": st.column_config.TextColumn(width="small"),
                "Блюдо A": st.column_config.TextColumn(width="large"),
                "Блюдо B": st.column_config.TextColumn(width="large"),
                "Вегетарианское": st.column_config.TextColumn(width="small"),
                "Жалоба": st.column_config.TextColumn(width="medium"),
            },
        )

    if report is not None:
        with st.container(border=True, key="home-savings-card"):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.subheader("Сценарии экономии (расчётные)")
                for s in report["scenarios"]:
                    st.write(
                        f"- до {s['target']}% отходов: экономия в неделю {fmt_money(s['saving_week'])} сом, "
                        f"за год {fmt_money(s['saving_year'])} сом"
                    )
            with col_b:
                st.caption(
                    "Потенциальная экономия — расчётный сценарий, а не подтверждённый результат. "
                    "Используются только тестовые данные."
                )

    with st.expander("О системе"):
        st.success("CLI доступен: python app.py all (через python3 .venv)")
        st.success("База данных SQLite инициализирована")
        saved = get_saved_menu()
        if saved:
            st.info("Используется сохранённое меню (в том числе после AI-генерации).")
        else:
            st.info("Используется встроенное демонстрационное меню.")
        st.warning("Реальные персональные данные не собираются; полноценная авторизация — следующий этап.")


def _veg_label(item):
    a = item.get("dish_a_vegetarian")
    b = item.get("dish_b_vegetarian")
    if a and b:
        return "A и B"
    if a:
        return "A"
    if b:
        return "B"
    return "—"


def page_menu():
    st.title("Меню на 5 дней")
    st.caption("Текущее активное меню: сохранённое, сгенерированное AI или встроенное демонстрационное.")
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
                    "Стоимость, сом": "не указано" if cost is None else (
                        str(int(cost)) if isinstance(cost, (int, float)) and not isinstance(cost, bool) and float(
                            cost).is_integer() else str(cost)
                    ),
                }
            )
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "День": st.column_config.TextColumn(width="small"),
            "Блюдо": st.column_config.TextColumn(width="large"),
            "Вегетарианское": st.column_config.TextColumn(width="small"),
            "Жалоба": st.column_config.TextColumn(width="medium"),
            "Стоимость, сом": st.column_config.TextColumn(width="small"),
        },
    )
    ok, errors = validate_menu(menu)
    if ok:
        st.success("Структура меню корректна: 5 дней, по 2 блюда, есть вегетарианский вариант.")
    else:
        st.error("; ".join(errors))


def page_orders():
    st.title("Заказы (ручной ввод)")
    st.caption("Инструмент администратора/демонстрации. Ученики заказывают через Telegram-бота; здесь можно вручную добавить тестовые заказы.")

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
        format_func=lambda x: dish_labels[x] if dish_labels[x].startswith("Блюдо ") else f"{x} — {dish_labels[x]}",
        horizontal=True,
    )

    if st.button("Сохранить заказ", type="primary"):
        if not STUDENT_CODE_RE.match(student_code.strip()):
            st.error("Код должен содержать 3-20 символов: буквы, цифры или дефис.")
        else:
            try:
                with st.spinner("Сохранение..."):
                    save_order(student_code.strip(), meal_date.isoformat(), dish)
                st.success(
                    "Заказ сохранён. Повторный выбор того же кода на эту дату обновит заказ, а не создаст дубликат.")
            except ValueError as exc:
                st.error(str(exc))

    existing = [o for o in get_orders(meal_date.isoformat()) if o["student_code"] == student_code.strip()]
    if existing:
        st.info(f"Текущий заказ на {meal_date.isoformat()}: блюдо {existing[0]['dish']}.")


def page_kitchen():
    st.title("Сводка для повара")
    for flash_key in ("demo_reset_flash", "demo_orders_flash"):
        flash = st.session_state.pop(flash_key, None)
        if flash:
            kind, message = flash
            (st.success if kind == "success" else st.error)(message)

    meal_date = st.date_input("Дата сводки", value=date.today(), key="kitchen_date")
    expected = st.number_input("Ожидаемое число обедающих", min_value=0, value=500, step=10)
    hist_mode = st.selectbox(
        "Распределение не ответивших",
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
    summary = kitchen_summary(counts["orders"], expected, veg_letters, historical_shares=None,
                              default_choice=historical)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Заказов A", summary["a_orders"])
    c2.metric("Заказов B", summary["b_orders"])
    c3.metric("Вегетарианских", summary["vegetarian_orders"])
    c4.metric("Не ответили", summary["unanswered"])

    c5, c6, c7 = st.columns(3)
    c5.metric("Базовые порции", summary["base_portions"])
    c6.metric("Резерв 5%, порций", summary["buffer"])
    c7.metric("Итого порций", summary["total_portions"])

    if counts["total"] == 0:
        st.info("Заказов на выбранную дату пока нет. Можно загрузить тестовые данные ниже.")

    st.write(
        f"Распределение по заказам: A — {summary['a_orders']}, B — {summary['b_orders']}. "
        "Неответившие не распределяются по блюдам автоматически."
    )
    if summary["unknown_distribution"] > 0:
        st.warning(
            f"Исторические доли неизвестны: показано общее количество необходимых порций "
            f"({summary['unknown_distribution']} не ответивших) отдельно от распределения A/B."
        )
    if historical:
        st.info("Оценочное распределение не ответивших включено в порции A/B как допущение, а не измерение.")
    if expected == 0:
        st.warning("Укажите ожидаемое число обедающих, иначе расчёт неполный.")

    if summary["total_orders"] == 0:
        st.info("Заказов на дату пока нет. Загрузите тестовые данные ниже или дождитесь предзаказов.")
    with st.expander("Telegram-рассылка (утренняя процедура)"):
        import os

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            st.info("TELEGRAM_BOT_TOKEN не задан: рассылка недоступна.")
        else:
            if st.button("Отправить утреннюю рассылку сейчас", key="tg_broadcast_now"):
                try:
                    from services.telegram_bot import run_daily_job

                    result = run_daily_job()
                    st.success(
                        f"Меню отправлено: {result['menu_sent']}; сводка отправлена: {result['summary_sent']}."
                    )
                except Exception as exc:
                    st.error(f"Не удалось выполнить рассылку: {exc}")
            st.caption("Планировщик: python bot.py schedule (по умолчанию в 09:00).")

    with st.expander("Тестовые данные"):
        if st.button("Загрузить тестовые заказы на выбранную дату"):
            try:
                with st.spinner("Загрузка..."):
                    seed_demo_orders(date_str)
                st.session_state["demo_orders_flash"] = ("success", "Тестовые заказы добавлены.")
            except Exception as exc:
                st.session_state["demo_orders_flash"] = ("error", f"Не удалось загрузить тестовые заказы: {exc}")
            st.rerun()
        reset_confirmed = st.checkbox(
            "Подтверждаю очистку заказов, стоимостей блюд и остатков",
            key="reset_confirmed",
        )
        st.button(
            "Очистить заказы, стоимости и остатки",
            disabled=not reset_confirmed,
            on_click=_reset_demo_data,
            key="reset_demo_data",
        )
        st.caption("Сохранённое меню (в том числе после AI-генерации) не удаляется.")


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
            with st.spinner("Сохранение..."):
                save_leftover(record_date.isoformat(), waste_mass, int(leftover_portions), note)
            st.success("Запись сохранена.")
        except Exception as exc:
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
            width="stretch",
            hide_index=True,
            column_config={
                "Дата": st.column_config.TextColumn(width="small"),
                "Отходы, кг": st.column_config.NumberColumn(width="small"),
                "Порций осталось": st.column_config.NumberColumn(width="small"),
                "Примечание": st.column_config.TextColumn(width="large"),
            },
        )
        masses = [r["waste_mass_kg"] for r in records if r["waste_mass_kg"] is not None]
        if masses:
            avg = sum(masses) / len(masses)
            st.metric("Средняя масса отходов по записям, кг", f"{avg:.1f}")
            st.caption(
                "Базовая оценка кейса — около 60 кг/день. Сравнение возможно только при достаточном числе записей.")
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
        width="stretch",
        hide_index=True,
        column_config={
            "День": st.column_config.TextColumn(width="small"),
            "Отходы, %": st.column_config.NumberColumn(width="small"),
            "Потери, сом": st.column_config.TextColumn(width="small"),
        },
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Неделя, сом", fmt_money(report["week_total"]))
    c2.metric("Год (продукты), сом", fmt_money(report["year_waste"]))
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
        width="stretch",
        hide_index=True,
        column_config={
            "Цель по отходам": st.column_config.TextColumn(width="small"),
            "Экономия в неделю, сом": st.column_config.TextColumn(width="small"),
            "Экономия за год, сом": st.column_config.TextColumn(width="small"),
        },
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
    flash = st.session_state.pop("costs_flash", None)
    if flash:
        kind, message = flash
        (st.success if kind == "success" else st.error)(message)

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

    st.caption("Отметьте «известна», чтобы учесть стоимость. Значение 0 может быть валидной ценой.")
    if st.button("Сохранить стоимости", type="primary"):
        try:
            for (day, letter), (val, known) in edited.items():
                with st.spinner("Сохранение..."):
                    save_dish_cost(day, letter, val if known else None)
            st.session_state["costs_flash"] = ("success", "Стоимости сохранены локально.")
        except Exception as exc:
            st.session_state["costs_flash"] = ("error", str(exc))
        st.rerun()

    saved = get_dish_costs()
    cost_dict = {}
    for m in get_active_menu():
        cost_dict[m["day"]] = {
            "A": saved.get((m["day"], "A")),
            "B": saved.get((m["day"], "B")),
        }

    report = check_budget(cost_dict, menu=get_active_menu())
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
        width="stretch",
        hide_index=True,
        column_config={
            "День": st.column_config.TextColumn(width="small"),
            "Блюдо": st.column_config.TextColumn(width="small"),
            "Стоимость": st.column_config.TextColumn(width="small"),
            "Статус": st.column_config.TextColumn(width="medium"),
        },
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
        st.warning(
            "AI-провайдер не настроен. Задайте AI_API_KEY (или OPENAI_API_KEY). Приложение продолжает работать на сохранённом меню.")

    col1, col2 = st.columns(2)
    generate_clicked = col1.button("Сформировать предложение меню")
    template_clicked = col2.button("Показать демонстрационный шаблон")

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
        if st.session_state.get("ai_result"):
            st.warning("Демонстрационный шаблон заменит текущее предложение меню.")
        result = demo_template_menu()
        st.session_state["ai_result"] = result
        st.info("Показан демонстрационный шаблон. Это не результат обращения к языковой модели.")

    result = st.session_state.get("ai_result")
    if not result:
        st.info("Нажмите одну из кнопок выше, чтобы получить предложение меню.")
    if result:
        st.subheader("Предпросмотр меню")
        st.caption(f"Источник: {result['source']} (provider={result.get('provider')}, model={result.get('model')})")
        st.dataframe(
            [
                {
                    "День": m["day"],
                    "Блюдо A": m["dish_a"],
                    "Блюдо B": m["dish_b"],
                    "Вегетарианское": _veg_label(m),
                    "Жалоба": m["complaint_cluster"],
                }
                for m in result["menu"]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "День": st.column_config.TextColumn(width="small"),
                "Блюдо A": st.column_config.TextColumn(width="large"),
                "Блюдо B": st.column_config.TextColumn(width="large"),
                "Вегетарианское": st.column_config.TextColumn(width="small"),
                "Жалоба": st.column_config.TextColumn(width="medium"),
            },
        )
        ok, errors = validate_ai_menu(result["menu"])
        if ok:
            st.success("Структура ответа корректна.")
        else:
            st.error("; ".join(errors))

        if result["source"] == "ai" and st.button("Сохранить как текущее меню", type="primary"):
            try:
                with st.spinner("Сохранение..."):
                    save_menu(result["menu"])
                st.success("Меню сохранено. Обновите страницу «Меню».")
            except ValueError as exc:
                st.error(str(exc))
        if result["source"] != "ai":
            st.caption("Демонстрационный шаблон нельзя сохранить как текущее меню — сформируйте меню через AI.")

        if result.get("raw_text"):
            with st.expander("Сырой ответ модели"):
                st.code(result["raw_text"])


PAGES = ["Главная", "Меню", "Заказы", "Кухня", "Остатки", "Экономика", "Проверка бюджета", "AI-меню"]


def main():
    init_db()
    if "page" not in st.session_state:
        qp = st.query_params.get("page")
        st.session_state["page"] = qp if qp in PAGES else "Главная"
    with st.sidebar:
        st.markdown("### 🍽️ Умная столовая")
        st.caption("Планирование меню, предзаказ и экономика столовой")
        st.divider()
        page = st.session_state.get("page", "Главная")
        if page not in PAGES:
            page = "Главная"
            st.session_state["page"] = page
        for item in PAGES:
            if st.button(
                    item,
                    key=f"nav_{item}",
                    type="primary" if item == page else "secondary",
                    width="stretch",
            ):
                st.session_state["page"] = item
                page = item
                try:
                    st.query_params["page"] = item
                except Exception:
                    pass
                st.rerun()
        try:
            st.query_params["page"] = page
        except Exception:
            pass
        st.divider()
        try:
            _cfg = get_ai_config()
            if _cfg["configured"]:
                st.success(f"AI: {_cfg['provider']}/{_cfg['model']}")
            else:
                st.warning("AI: не настроен")
        except Exception:
            st.info("AI: статус неизвестен")
        st.caption("v1.0 · локальный прототип")

    if page == "Главная":
        page_home()
    elif page == "Меню":
        page_menu()
    elif page == "Заказы":
        page_orders()
    elif page == "Кухня":
        page_kitchen()
    elif page == "Остатки":
        page_leftovers()
    elif page == "Экономика":
        page_economics()
    elif page == "Проверка бюджета":
        page_budget()
    else:
        page_ai()


if __name__ == "__main__":
    main()
