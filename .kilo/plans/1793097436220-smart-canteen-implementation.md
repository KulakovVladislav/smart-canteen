# Plan: Smart Canteen (Кейс «Умная столовая») implementation

## Goal

Deliver a hackathon-ready demo that turns student complaint clusters into a 5-day menu, validates budget constraints,
and demonstrates a preorder flow with a kitchen summary. All facts come from the concept file and existing data; no
fabricated prices.

## Current state

- Data and economics already present: `data/input.md`, `data/waste_by_day.csv`, `data/complaints.csv`,
  `src/waste_calc.py`, `docs/economics_review.md`.
- Empty placeholders: `app.py`, `src/menu.py`, `src/preorder.py`, `src/economics.py`.
- No system prompt file, menu artifact, bot dialog artifact, or budget check yet.

## Phases

### Phase 1: Research and source lock

- Re-read concept file and existing data; confirm no new assumptions.
- Lock complaint wording and waste percentages as immutable inputs.
- Output: no code; checklist in plan.

### Phase 2: Architecture and data contracts

- Define minimal file layout:
    - `prompts/system_prompt.md` — six-block AI prompt.
    - `docs/menu.md` — complaint-to-menu mapping and 5-day menu.
    - `docs/bot_dialog.md` — example dialog and summary format.
    - `src/preorder.py` — preorder counting and summary generation.
    - `src/menu.py` — menu data structures and budget validator interface.
    - `src/economics.py` — thin wrapper calling `waste_calc` helpers (no duplicate logic).
    - `app.py` — CLI entry point.
- Data contracts:
    - Menu item: `{day, dish_a, dish_b, complaint_cluster, cost_assumption_note}`.
    - Preorder input: list of choices A/B per student; output counts and 5% buffer.

### Phase 3: Development

1. Write system prompt markdown (six blocks exactly as concept).
2. Write menu markdown (verbatim complaint wording, 5-day table, cost ceiling note).
3. Implement `src/preorder.py`:
    - Parse a small sample preorder list.
    - Count A/B, vegetarian (B), unanswered, buffer 5%, total portions.
    - Print summary in concept format.
    - Handle empty input and invalid choices.
4. Implement `src/menu.py`:
    - Store menu as data.
    - Validate: 5 days, 2 dishes/day, one meatless/day.
    - Budget validator accepts provided per-dish cost and checks <= 140; marks unknown costs as "не указано".
5. Implement `app.py` CLI:
    - Commands: `menu`, `preorder`, `budget-check`, `all`.
    - No external dependencies.

### Phase 4: Testing

- Add `tests/test_preorder.py`, `tests/test_menu.py` using stdlib `unittest`.
- Test counts, buffer math, validation rules, edge cases.
- Run `python -m unittest`.

### Phase 5: Deployment/demo

- Update `README.md` with run commands (already has basic; extend).
- Smoke test: `python app.py all`.
- Prepare demo outputs for jury.

## Affected boundaries

- Only existing empty modules plus new markdown files; do not touch economics data or `waste_calc.py`.

## Risks

- No real price data: budget check must remain a validator, not a fabricated estimate.
- Bot is demo-only; no Telegram integration in MVP.
- Keep stdlib only.

## Validation

- Unit tests pass.
- `python app.py all` prints menu, preorder summary, budget status.
- Manual review against concept file.

## Open questions

1. Should the demo include a simple HTTP page, or CLI only? (Recommendation: CLI only for hackathon speed.)
2. Should preorder sample data be hardcoded or read from a CSV? (Recommendation: hardcoded sample in `src/preorder.py`
   plus optional CSV path.)
