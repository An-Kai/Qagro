"""journal.py — журнал наблюдений фермера (Qagro platform v4).

Та же SQLite БД что и «Мои поля» (data/myfields.db), таблица notes:
    notes(id, field_id, date, problem_type, text)

Функции:
    add_note(field_id, problem_type, text, date=None, db_path=None) -> dict
    list_notes(field_id, db_path=None) -> list[dict]

problem_type строго из списка:
    weeds / pests / disease / lodging / drought / other
Нарушение -> ValueError. Подписи типов RU/KZ/EN — PROBLEM_TYPES.
Только sqlite3, без сети.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "myfields.db"

PROBLEM_TYPES: dict[str, dict[str, str]] = {
    "weeds": {"ru": "Сорняки", "kz": "Арамшөптер", "en": "Weeds"},
    "pests": {"ru": "Вредители", "kz": "Зиянкестер", "en": "Pests"},
    "disease": {"ru": "Болезнь", "kz": "Ауру", "en": "Disease"},
    "lodging": {"ru": "Полегание", "kz": "Жату", "en": "Lodging"},
    "drought": {"ru": "Засуха", "kz": "Құрғақшылық", "en": "Drought"},
    "other": {"ru": "Прочее", "kz": "Басқа", "en": "Other"},
}

SCHEMA_NOTES = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    problem_type TEXT NOT NULL,
    text TEXT NOT NULL
)
"""

SCHEMA_FIELDS_MIN = """
CREATE TABLE IF NOT EXISTS fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    area_ha REAL NOT NULL,
    crop TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _db_file(db_path: str | Path | None) -> Path:
    p = Path(db_path) if db_path is not None else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(_db_file(db_path)))
    con.row_factory = sqlite3.Row
    return con


def init_db(db_path: str | Path | None = None) -> Path:
    """Создать таблицу notes (и fields-заглушку) если их нет."""
    p = _db_file(db_path)
    con = _connect(p)
    try:
        con.execute(SCHEMA_FIELDS_MIN)
        con.execute(SCHEMA_NOTES)
        con.commit()
    finally:
        con.close()
    return p


def problem_label(problem_type: str, lang: str = "ru") -> str:
    """Подпись типа проблемы на ru/kz/en. Неизвестный тип -> ValueError."""
    if problem_type not in PROBLEM_TYPES:
        raise ValueError(
            f"problem_type={problem_type!r} неизвестен. "
            f"Допустимо: {sorted(PROBLEM_TYPES)}."
        )
    lang = (lang or "ru").lower()
    if lang not in ("ru", "kz", "en"):
        raise ValueError(f"lang={lang!r} недопустим. Допустимо: ru, kz, en.")
    return PROBLEM_TYPES[problem_type][lang]


def add_note(
    field_id: int,
    problem_type: str,
    text: str,
    date: str | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Добавить заметку к полю. Возвращает dict записи (включая id)."""
    try:
        fid = int(field_id)
    except (TypeError, ValueError):
        raise ValueError(f"field_id={field_id!r} не целое.") from None
    if problem_type not in PROBLEM_TYPES:
        raise ValueError(
            f"problem_type={problem_type!r} неизвестен. "
            f"Допустимо: {sorted(PROBLEM_TYPES)}."
        )
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text пустой: опишите проблему.")
    day = date if date is not None else str(date_class_today())
    if not isinstance(day, str) or not day.strip():
        raise ValueError(f"date={date!r} некорректна (ожидается 'YYYY-MM-DD').")
    day = day.strip()
    init_db(db_path)
    con = _connect(db_path)
    try:
        exists = con.execute(
            "SELECT 1 FROM fields WHERE id = ?", (fid,)
        ).fetchone()
        if exists is None:
            raise ValueError(f"field_id={fid} не найден в таблице fields.")
        cur = con.execute(
            "INSERT INTO notes (field_id, date, problem_type, text)"
            " VALUES (?, ?, ?, ?)",
            (fid, day, problem_type, text.strip()),
        )
        con.commit()
        new_id = int(cur.lastrowid)
        row = con.execute(
            "SELECT id, field_id, date, problem_type, text"
            " FROM notes WHERE id = ?",
            (new_id,),
        ).fetchone()
    finally:
        con.close()
    return dict(row)


def list_notes(
    field_id: int, db_path: str | Path | None = None
) -> list[dict]:
    """Все заметки поля, сортировка по id."""
    try:
        fid = int(field_id)
    except (TypeError, ValueError):
        raise ValueError(f"field_id={field_id!r} не целое.") from None
    init_db(db_path)
    con = _connect(db_path)
    try:
        cur = con.execute(
            "SELECT id, field_id, date, problem_type, text"
            " FROM notes WHERE field_id = ? ORDER BY id",
            (fid,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def date_class_today() -> str:
    return date.today().isoformat()


if __name__ == "__main__":  # smoke: python src/journal.py
    try:
        from src.myfields import add_field, delete_field
    except ImportError:
        from myfields import add_field, delete_field  # type: ignore
    f = add_field("Тест-Журнал", 51.95, 66.40, 50.0, "barley")
    n = add_note(f["id"], "weeds", "Осот по краю поля")
    print("added note:", n)
    print("notes:", list_notes(f["id"]))
    print("deleted field:", delete_field(f["id"]))
