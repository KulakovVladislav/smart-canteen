# -*- coding: utf-8 -*-
"""Веб-приложение Streamlit для «Умной столовой»."""

import os
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
    save_dish_costs,
    save_leftover,
    save_menu,
    seed_demo_orders,
    seed_presentation_data,
)

CUSTOM_CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.css")
try:
    with open(CUSTOM_CSS_PATH, encoding="utf-8") as _f:
        CUSTOM_CSS = _f.read()
except FileNotFoundError:
    CUSTOM_CSS = ""


def fmt_money(x):
    return f"{x:,.0f}".replace(",", " ")


def fmt_money_short(value):
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}".replace(".", ",") + " млн"
    if abs(value) >= 10_000:
        return f"{value / 1_000:.1f}".replace(".", ",") + " тыс."
    return fmt_money(value)


def status_for_budget(report):
    if report["has_over_limit"]:
        return "ПРЕВЫШЕНИЕ ЛИМИТА"
    if report["has_unknown"]:
        return "НЕДОСТАТОЧНО ДАННЫХ"
    return "OK"


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


def _seed_presentation_data(meal_date):
    try:
        seeded = seed_presentation_data(meal_date.isoformat())
        st.session_state["demo_seed_flash"] = (
            "success",
            f"Демонстрационный набор готов: {seeded['orders']} предзаказов, "
            f"{seeded['costs']} стоимостей и {seeded['leftovers']} измерения остатков.",
        )
    except Exception as exc:
        st.session_state["demo_seed_flash"] = ("error", f"Не удалось подготовить набор: {exc}")


def page_home():
    st.title("Обзор столовой")
    st.caption("Меню, потери и контроль расходов в одном месте.")

    all_orders = get_orders()
    try:
        report = waste_report()
    except (OSError, ValueError) as exc:
        report = None
        st.warning(f"Данные об отходах недоступны: {exc}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Заказов в базе", len(all_orders))
    col2.metric("Потери за неделю", "—" if report is None else f"{fmt_money_short(report['week_total'])} сом")
    col3.metric("Потери за год", "—" if report is None else f"{fmt_money_short(report['year_waste'])} сом")

    with st.container(border=True, key="home-menu-card"):
        st.subheader("Меню на неделю")
        menu = get_active_menu()
        st.dataframe(
            [
                {
                    "День": {
                        "Понедельник": "Пн",
                        "Вторник": "Вт",
                        "Среда": "Ср",
                        "Четверг": "Чт",
                        "Пятница": "Пт",
                    }.get(item["day"], item["day"]),
                    "Блюдо A": item["dish_a"],
                    "Блюдо B": item["dish_b"],
                }
                for item in menu
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "День": st.column_config.TextColumn(width="small"),
                "Блюдо A": st.column_config.TextColumn(width="large"),
                "Блюдо B": st.column_config.TextColumn(width="large"),
            },
        )

    if report is not None:
        with st.container(border=True, key="home-savings-card"):
            st.subheader("Сценарии экономии")
            st.dataframe(
                [
                    {
                        "Цель по отходам": f"до {scenario['target']}%",
                        "Экономия в неделю": f"{fmt_money(scenario['saving_week'])} сом",
                        "Экономия за год": f"{fmt_money(scenario['saving_year'])} сом",
                    }
                    for scenario in report["scenarios"]
                ],
                width="stretch",
                hide_index=True,
            )
            st.caption("Расчёт на модельных данных — это прогноз, а не фактическая экономия.")

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


def page_menu(show_costs=True):
    st.title("Меню на неделю")
    st.caption("Блюда по дням, отметки о вегетарианском варианте и себестоимость.")
    menu = get_active_menu()
    costs = get_dish_costs()
    rows = []
    for item in menu:
        for letter, dish_key, vegetarian_key in (
            ("A", "dish_a", "dish_a_vegetarian"),
            ("B", "dish_b", "dish_b_vegetarian"),
        ):
            price = costs.get((item["day"], letter))
            rows.append(
                {
                    "День и вариант": f"{item['day']} · {letter}",
                    "Блюдо": item[dish_key],
                    "Вегетарианское": "Да" if item.get(vegetarian_key) else "Нет",
                    "Себестоимость": f"{fmt_money(price)} сом" if show_costs and price is not None else "Не указана",
                }
            )
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "День и вариант": st.column_config.TextColumn(width="medium"),
            "Блюдо": st.column_config.TextColumn(width="large"),
            "Вегетарианское": st.column_config.TextColumn(width="small"),
            "Себестоимость": st.column_config.TextColumn(width="small"),
        },
    )
    with st.expander("Пожелания, учтённые в меню"):
        st.dataframe(
            [
                {"День": item["day"], "Пожелание": item.get("complaint_cluster") or "Не указано"}
                for item in menu
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "День": st.column_config.TextColumn(width="small"),
                "Пожелание": st.column_config.TextColumn(width="large"),
            },
        )
    ok, errors = validate_menu(menu)
    if ok:
        st.success("Меню прошло проверку: 5 учебных дней, по 2 блюда в каждом.")
    else:
        st.error("; ".join(errors))


def page_kitchen():
    st.title("Сводка для повара")
    for flash_key in ("demo_reset_flash", "demo_orders_flash", "demo_seed_flash"):
        flash = st.session_state.pop(flash_key, None)
        if flash:
            kind, message = flash
            (st.success if kind == "success" else st.error)(message)

    date_col, expected_col = st.columns(2)
    meal_date = date_col.date_input("Дата приготовления", value=date.today(), key="kitchen_date")
    expected = expected_col.number_input("Ожидается обедающих", min_value=0, value=500, step=10)
    hist_mode = st.selectbox(
        "Если нет ответа",
        ["Не распределять", "Считать выбором A", "Считать выбором B", "Разделить поровну"],
        index=0,
    )
    hist_map = {
        "Не распределять": None,
        "Считать выбором A": "A",
        "Считать выбором B": "B",
        "Разделить поровну": "split",
    }
    historical = hist_map[hist_mode]

    date_str = meal_date.isoformat()
    counts = count_orders(date_str)
    day_name = day_for_date(meal_date)
    veg_letters = vegetarian_letters_for_day(day_name, menu=get_active_menu()) if day_name else []
    summary = kitchen_summary(counts["orders"], expected, veg_letters, historical_shares=None,
                              default_choice=historical)

    st.subheader(f"План приготовления · {day_name or 'выходной'}")
    menu_for_day = next((item for item in get_active_menu() if item["day"] == day_name), None)
    if menu_for_day:
        st.dataframe(
            [
                {
                    "Вариант": letter,
                    "Блюдо": menu_for_day[dish_key],
                    "Заказано": summary[count_key],
                    "Вегетарианское": "Да" if menu_for_day.get(vegetarian_key) else "Нет",
                }
                for letter, dish_key, count_key, vegetarian_key in (
                    ("A", "dish_a", "a_orders", "dish_a_vegetarian"),
                    ("B", "dish_b", "b_orders", "dish_b_vegetarian"),
                )
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("На выбранную дату нет меню учебного дня.")

    c1, c2 = st.columns(2)
    c1.metric("Выбор A", summary["a_orders"])
    c2.metric("Выбор B", summary["b_orders"])

    c3, c4 = st.columns(2)
    c3.metric("Вег. выборы", summary["vegetarian_orders"])
    c4.metric("Без ответа", summary["unanswered"])

    c5, c6, c7 = st.columns(3)
    c5.metric("Базовые порции", summary["base_portions"])
    c6.metric("Резерв, порций", summary["buffer"], help="5% от базового числа порций")
    c7.metric("Всего порций", summary["total_portions"])

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
        st.caption("Набор заменяет только заказы, стоимости и остатки. Сохранённое меню и подписки бота остаются без изменений.")
        st.button(
            "Подготовить набор для презентации",
            type="primary",
            on_click=_seed_presentation_data,
            args=(meal_date,),
            key="seed_presentation_data",
        )
        if st.button("Загрузить тестовые заказы на выбранную дату"):
            try:
                with st.spinner("Загрузка…"):
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
            with st.spinner("Сохранение…"):
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
                    "Дата": record["record_date"],
                    "Отходы, кг": record["waste_mass_kg"],
                    "Порций осталось": record["leftover_portions"],
                    "Примечание": record.get("note") or "—",
                }
                for record in records[:20]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "Дата": st.column_config.TextColumn(width="small"),
                "Отходы, кг": st.column_config.NumberColumn(width="small", format="%.1f"),
                "Порций осталось": st.column_config.NumberColumn(width="small", format="%d"),
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
    c1, c2, c3 = st.columns(3)
    c1.metric("Неделя, сом", fmt_money(report["week_total"]))
    c2.metric("Год (продукты), сом", fmt_money(report["year_waste"]))
    c3.metric("Утилизация за год, сом", fmt_money(report["util_year"]))

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

    measured = get_leftovers()
    measured_masses = [row["waste_mass_kg"] for row in measured if row["waste_mass_kg"] is not None]
    st.subheader("Фактические измерения")
    if measured_masses:
        average_mass = sum(measured_masses) / len(measured_masses)
        benchmark = report["assumptions"]["waste_kg_per_day"]
        difference = average_mass - benchmark
        actual_1, actual_2, actual_3 = st.columns(3)
        actual_1.metric("Средние отходы", f"{average_mass:.1f} кг")
        actual_2.metric(
            "К базовой оценке",
            f"{abs(difference):.1f} кг {'выше' if difference > 0 else 'ниже' if difference < 0 else 'без изменений'}",
        )
        actual_3.metric("Измерений", len(measured_masses))
        st.caption(
            f"Фактическая масса сравнивается с ориентиром кейса {benchmark:.0f} кг/день. "
            "Денежные сценарии выше остаются модельными, пока не собрана финансовая первичка."
        )
        st.dataframe(
            [{"Дата": row["record_date"], "Отходы, кг": row["waste_mass_kg"], "Осталось порций": row["leftover_portions"]}
             for row in measured[:20]],
            width="stretch", hide_index=True,
        )
    else:
        st.info("Пока нет измерений. Внесите массу отходов на странице «Остатки», чтобы начать сравнение.")

    with st.expander("Исходные допущения"):
        st.markdown(
            f"- Процент отходов применяется к дневному бюджету закупок {fmt_money(report['assumptions']['budget_per_day'])} сом (упрощённое допущение).\n"
            "- Стоимость потерянных продуктов и утилизация показаны отдельно, чтобы избежать двойного учёта.\n"
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
    st.subheader("Стоимость блюд")
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
            with st.spinner("Сохранение…"):
                save_dish_costs({key: val if known else None for key, (val, known) in edited.items()})
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
                with st.spinner("Обращение к языковой модели…"):
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
        ok, errors = validate_ai_menu(result["menu"], costs=get_dish_costs())
        if ok:
            st.success("Структура ответа корректна.")
        else:
            st.error("; ".join(errors))

        if result["source"] == "ai" and st.button("Сохранить как текущее меню", type="primary"):
            try:
                with st.spinner("Сохранение…"):
                    save_menu(result["menu"])
                st.success("Меню сохранено. Обновите страницу «Меню».")
            except ValueError as exc:
                st.error(str(exc))
        if result["source"] != "ai":
            st.caption("Демонстрационный шаблон нельзя сохранить как текущее меню — сформируйте меню через AI.")

        if result.get("raw_text"):
            with st.expander("Сырой ответ модели"):
                st.code(result["raw_text"])


ROLE_PAGES = {
    "Управление": ["Главная", "Меню", "Экономика", "Проверка бюджета", "AI-меню"],
    "Кухня": ["Кухня", "Остатки", "Меню"],
}


def _web_access_allowed():
    """Optional local gate for a shared staff workstation.

    It stays disabled by default so the prototype remains easy to run locally.
    A real deployment must set ``CANTEEN_WEB_ACCESS_CODE`` and use HTTPS.
    """
    configured_code = os.environ.get("CANTEEN_WEB_ACCESS_CODE", "").strip()
    if not configured_code:
        return True
    if st.session_state.get("web_access_granted"):
        return True
    st.title("Вход для сотрудников")
    st.caption("Этот рабочий кабинет предназначен для кухни и управляющих.")
    entered_code = st.text_input("Код доступа", type="password")
    if st.button("Открыть кабинет", type="primary"):
        if entered_code == configured_code:
            st.session_state["web_access_granted"] = True
            st.rerun()
        st.error("Код доступа не подошёл.")
    return False


def inject_styles():
    if CUSTOM_CSS:
        st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="Умная столовая", page_icon="🍽️", layout="wide")
    inject_styles()
    init_db()
    if not _web_access_allowed():
        return
    with st.sidebar:
        st.markdown("### 🍽️ Умная столовая")
        if "site_role" not in st.session_state:
            initial_page = st.session_state.get("page") or st.query_params.get("page")
            initial_role = next((name for name, role_pages in ROLE_PAGES.items() if initial_page in role_pages), "Управление")
            st.session_state["site_role"] = initial_role
        role = st.radio("Рабочий раздел", list(ROLE_PAGES), key="site_role")
        pages = ROLE_PAGES[role]
        if "page" not in st.session_state or st.session_state["page"] not in pages:
            requested = st.query_params.get("page")
            st.session_state["page"] = requested if requested in pages else pages[0]
        st.divider()
        page = st.session_state.get("page", "Главная")
        if page not in pages:
            page = pages[0]
            st.session_state["page"] = page
        for item in pages:
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
                st.caption("AI: настроен")
            else:
                st.caption("AI: демо-режим")
        except Exception:
            st.caption("AI: статус неизвестен")
        st.caption("v1.0 · локальный прототип")
        if os.environ.get("CANTEEN_WEB_ACCESS_CODE", "").strip():
            st.caption("Доступ ограничен кодом сотрудника")
        else:
            st.caption("Локальный режим · разделы не являются правами доступа")

    if page == "Главная":
        page_home()
    elif page == "Меню":
        page_menu()
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
