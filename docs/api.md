# Публичный API «Умная столовая»

## domain.menu

- `get_menu(db_path=None)` — список блюд по дням.
- `get_active_menu(db_path=None)` — активное меню (из БД или дефолт).
- `validate_menu(menu=None) -> (bool, list[str])`
- `is_valid_menu(menu=None) -> bool`
- `check_budget(costs=None, limit=COST_CEILING, menu=None) -> dict`
- `day_for_date(value) -> str | None`
- `vegetarian_letters_for_day(day, menu=None) -> list[str]`

## domain.preorder

- `count_preorders(choices=None, ...) -> PreorderSummary`
- `kitchen_summary(orders, expected_diners, ...) -> KitchenSummary`
- `format_summary(counts, date="завтра") -> str`

## repositories.storage

- `init_db(db_path=None)`, `get_connection`, `get_db_path`
- orders, costs, leftovers, menu CRUD.

## services

- `ai_menu.generate_menu(...)`, `validate_ai_menu(...)`
- `telegram_bot.run_bot(...)`

Отдельные устаревшие имена функций в канонических модулях помечены `DeprecationWarning`. Обёртки `src/*` сами по себе не
выводят предупреждение.
