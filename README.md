# Smart Canteen

Smart Canteen is a school canteen optimization project that uses student complaint clusters to redesign the weekly menu and reduce food waste. It estimates savings from waste reduction and provides a preorder summary for kitchen staff.

## Folder structure

- `data/` — input data (case parameters, waste by day, complaints)
- `src/` — source code (waste calculation script)
- `docs/` — documentation
- `tests/` — tests



## Run

```bash
python app.py all          # menu + preorder summary + budget check + economics
python app.py menu         # 5-day menu
python app.py preorder     # preorder summary for kitchen
python app.py budget-check # budget validation
python src/waste_calc.py   # waste losses and savings scenarios
```

## Web app

```bash
pip install -r requirements.txt
streamlit run web_app.py
```

Локальная база SQLite: `data/smart_canteen.db` (создаётся автоматически).

## Ограничения безопасности

Локальный демонстрационный прототип: только тестовые данные, без реальных персональных данных, без полноценной авторизации и разграничения прав. Не открывать публично без проверки.
