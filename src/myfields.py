"""myfields.py — «Мои поля» фермера (Qagro platform v4).

SQLite БЕЗ сети, только stdlib sqlite3:
    data/myfields.db, таблица fields.

Функции:
    add_field(name, lat, lon, area_ha, crop, db_path=None) -> dict
    list_fields(db_path=None) -> list[dict]
    delete_field(field_id, db_path=None) -> bool

Валидация (Акмолинская область):
    lat 50..54, lon 65..72, area 1..2000 га, name/crop непустые.
Нарушение -> ValueError. Без моков и без внешних зависимостей.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "myfields.db"

LAT_MIN, LAT_MAX = 50.0, 54.0
LON_MIN, LON_MAX = 65.0, 72.0
AREA_MIN, AREA_MAX = 1.0, 2000.0

SCHEMA_FIELDS = """
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
    """Создать таблицу fields если её нет. Возвращает путь к БД."""
    p = _db_file(db_path)
    con = _connect(p)
    try:
        con.execute(SCHEMA_FIELDS)
        con.commit()
    finally:
        con.close()
    return p


def _validate(name: str, lat: float, lon: float, area_ha: float, crop: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name пустое: укажите название поля.")
    try:
        lat = float(lat)
    except (TypeError, ValueError):
        raise ValueError(f"lat={lat!r} не число.") from None
    try:
        lon = float(lon)
    except (TypeError, ValueError):
        raise ValueError(f"lon={lon!r} не число.") from None
    try:
        area_ha = float(area_ha)
    except (TypeError, ValueError):
        raise ValueError(f"area_ha={area_ha!r} не число.") from None
    if not (LAT_MIN <= lat <= LAT_MAX):
        raise ValueError(
            f"lat={lat} вне Акмолы: допустимо {LAT_MIN}..{LAT_MAX}."
        )
    if not (LON_MIN <= lon <= LON_MAX):
        raise ValueError(
            f"lon={lon} вне Акмолы: допустимо {LON_MIN}..{LON_MAX}."
        )
    if not (AREA_MIN <= area_ha <= AREA_MAX):
        raise ValueError(
            f"area_ha={area_ha} вне диапазона: допустимо {AREA_MIN}..{AREA_MAX} га."
        )
    if not isinstance(crop, str) or not crop.strip():
        raise ValueError("crop пустое: укажите культуру (напр. spring_wheat).")


def add_field(
    name: str,
    lat: float,
    lon: float,
    area_ha: float,
    crop: str,
    db_path: str | Path | None = None,
) -> dict:
    """Добавить поле. Возвращает dict созданной записи (включая id)."""
    _validate(name, lat, lon, area_ha, crop)
    init_db(db_path)
    con = _connect(db_path)
    try:
        cur = con.execute(
            "INSERT INTO fields (name, lat, lon, area_ha, crop, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                name.strip(),
                float(lat),
                float(lon),
                float(area_ha),
                crop.strip(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        con.commit()
        new_id = int(cur.lastrowid)
    finally:
        con.close()
    rows = [r for r in list_fields(db_path) if r["id"] == new_id]
    return rows[0] if rows else {"id": new_id}


def list_fields(db_path: str | Path | None = None) -> list[dict]:
    """Все поля фермера, сортировка по id."""
    init_db(db_path)
    con = _connect(db_path)
    try:
        cur = con.execute(
            "SELECT id, name, lat, lon, area_ha, crop, created_at"
            " FROM fields ORDER BY id"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def delete_field(field_id: int, db_path: str | Path | None = None) -> bool:
    """Удалить поле по id. True — удалено, False — такого id не было."""
    init_db(db_path)
    try:
        fid = int(field_id)
    except (TypeError, ValueError):
        raise ValueError(f"field_id={field_id!r} не целое.") from None
    con = _connect(db_path)
    try:
        cur = con.execute("DELETE FROM fields WHERE id = ?", (fid,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


if __name__ == "__main__":  # smoke: python src/myfields.py
    f = add_field("Тест-Поле", 51.95, 66.40, 100.0, "spring_wheat")
    print("added:", f)
    print("count:", len(list_fields()))
    print("deleted:", delete_field(f["id"]))
