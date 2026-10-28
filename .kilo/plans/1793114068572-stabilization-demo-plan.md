# Plan: Stabilization of Smart Canteen demo

## Goal
Stabilize the existing prototype for a demo: reconcile in-progress changes, keep all tests green, validate CLI and Streamlit entry points, and close obvious robustness gaps without changing core economics.

## Current state
- `python3 -m unittest`: 74 tests pass.
- `python app.py all`: works.
- Streamlit import works via `.venv/bin/python`.
- Uncommitted changes exist in `src/menu.py`, `src/telegram_bot.py`, `tests/test_menu.py`, `web_app.py` (design/CSS refactor and validation tightening).
- `src/menu.py` now uses strict `bool` for vegetarian flags; this may over-reject truthy values.

## Scope decisions
- Keep page naming as `Остатки` (renamed from `Отходы`).
- Keep stricter menu validation, but normalize truthy flags with `bool()` rather than `isinstance(bool)` to avoid breaking compatible inputs.
- No new dependencies; stdlib + existing Streamlit only.

## Tasks
1. Review uncommitted diff for accidental or partial edits; remove stray artifacts.
2. In `src/menu.py`, change vegetarian flag checks from strict `isinstance(bool)` to `bool()` conversion, while still requiring at least one vegetarian dish per day.
3. Update `tests/test_menu.py` to cover:
   - empty `complaint_cluster` rejection (if intended non-empty);
   - truthy/non-bool vegetarian flags normalization;
   - budget edge cases already present.
4. Ensure `src/telegram_bot.py` continues to use `get_active_menu(db_path=...)` for `/menu` and `/order` flows.
5. Smoke-test Streamlit with `.venv/bin/streamlit run web_app.py` in headless mode and fix any runtime errors.
6. Smoke-test CLI: `.venv/bin/python app.py all`.
7. Update `README.md` page names and note about using `.venv` Python if system Python lacks Streamlit.
8. Security/robustness pass: verify no secrets committed, SQL parameters used, student code validation remains.
9. Run full test suite and record result.

## Affected boundaries
- `src/menu.py`, `src/telegram_bot.py`, `tests/test_menu.py`, `web_app.py`, `README.md`.
- Do not modify `src/waste_calc.py` data or economics formulas.

## Risks
- Strict bool change could break hidden tests expecting integer flags; normalizing with `bool()` mitigates.
- Streamlit runtime warnings in bare import are expected and not failures.
- Uncommitted redesign may introduce CSS/runtime issues; smoke test required.

## Validation
- `python3 -m unittest` passes.
- `python app.py all` prints menu, preorder summary, budget status, economics.
- `.venv/bin/python -c "import web_app"` succeeds.
- Manual Streamlit smoke test (headless) completes without traceback.
