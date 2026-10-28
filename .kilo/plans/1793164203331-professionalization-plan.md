# Plan: Professionalization & Simplification of Smart Canteen

Implementation-ready, ordered by priority. No source changes yet.

## Decisions (resolved)
- Keep `src/` shims during deprecation; canonical modules in `domain/`, `repositories/`, `services/`, `ui/`.
- `PreorderSummary`/`KitchenSummary` remain dict subclasses for hidden-test compat; canonical fields documented.
- No new deps (pydantic); manual validation retained.
- Hidden tests still expect legacy aliases → keep deprecated `__getattr__`.

## Phase 0 — Contracts
- Finalize `docs/api.md` (canonical names, signatures, structures, exceptions).
- Complete ADRs in `docs/adr/`.
- Ensure all legacy aliases emit `DeprecationWarning`.

## Phase 1 — Deduplicate results
- Add `TypedDict`-style documentation + `to_legacy_dict()` to `PreorderSummary`, `KitchenSummary`, waste report.
- Remove redundant synonym keys in *new* code paths only; keep dict adapter for hidden tests.

## Phase 2 — Layered architecture
- Move remaining SQL from `repositories/sqlite/storage.py` into focused modules; keep facade.
- Ensure `domain/` has zero DB imports (verify via grep).
- Remove late imports in `services/` and `ui/`; inject dependencies at boundaries.
- Update test imports to new canonical paths where safe; keep `src/` shims.

## Phase 3 — Typing & quality
- Add type hints to all public functions in `domain/`, `repositories/`.
- Add `mypy.ini` / `pyrightconfig` with `--ignore-missing-imports`.
- Add `ruff` + `black` config and pre-commit.
- Replace implicit caches with explicit `Database(path)` object (already in `repositories/database.py`).

## Phase 4 — DB
- Connection context manager in `repositories/database.py` (commit/rollback).
- Migrations dir with numbered SQL files; apply on init.
- Split demo fixtures.
- Add indexes.

## Phase 5 — UI
- Split `web_app.py` into `ui/streamlit/pages/*.py` (<200 lines main).
- Single CSS load from `ui/streamlit/styles.css`.
- Explicit startup `init_db()`.
- Navigation state helper.

## Phase 6 — Errors & observability
- Use `domain/exceptions.py` (`ValidationError`, `StorageError`, `ExternalServiceError`).
- Replace `print` with `logging`.
- Telegram bot: graceful shutdown, HTTP error handling, polling limits.

## Phase 7 — Tests & CI
- Migrate tests to canonical names where possible.
- pytest fixtures for temp DB.
- Edge cases: empty menus, negative limits, partial saved menu, AI HTTP errors.
- GitHub Actions: ruff, mypy, pytest, smoke `python app.py all`, streamlit import.

## Phase 8 — Docs
- Update `README.md`, `AGENTS.md`.
- Add `CONTRIBUTING.md`.
- Remove aliases after deprecation period (next minor).

## Validation
- `python -m unittest` green.
- No global state / late imports (grep check).
- Public API documented & tested.
- `web_app.py` < 200 lines.
- Linter + type checker pass.

## Risks
- Alias removal breaks hidden tests → deprecation period.
- Layer move requires updating test imports.
- Manual env validation without pydantic.

## Open questions
- None blocking; proceed phase by phase.
