"""test_platform.py — тесты платформы фермера (Qagro v4), без pytest.

Запуск: python tests/test_platform.py
- assert + честный skip: spray при офлайне (RuntimeError) — SKIP, не FAIL.
- myfields/journal гоняются на временном SQLite-файле (изоляция),
  плюс проверка пути data/myfields.db по умолчанию.
- Роутер platform_api проверяется через TestClient на отдельном FastAPI
  приложении (src/api.py НЕ трогаем).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Windows-консоль (cp1251) не кодирует казахские буквы — не роняем тест
# на print-вердиктах, показываем их максимально читаемо.
try:
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                   errors="backslashreplace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import journal as J  # noqa: E402
from src import myfields as MF  # noqa: E402
from src import spray as SP  # noqa: E402

passed: list[str] = []
skipped: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
    except RuntimeError as e:
        if "SKIP-OFFLINE" in str(e):
            skipped.append(name)
            print(f"SKIP (offline): {name} — {e}".replace("SKIP-OFFLINE: ", ""))
            return
        raise
    passed.append(name)
    print(f"PASS: {name}")


def _tmpdb() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


# ------------------------------------------------------------ myfields
def t_field_crud():
    db = _tmpdb()
    try:
        f = MF.add_field("Тест-Поле", 51.95, 66.40, 100.0, "spring_wheat",
                         db_path=db)
        assert isinstance(f.get("id"), int), f
        assert f["name"] == "Тест-Поле" and f["crop"] == "spring_wheat", f
        rows = MF.list_fields(db_path=db)
        assert len(rows) == 1 and rows[0]["id"] == f["id"], rows
        assert MF.delete_field(f["id"], db_path=db) is True
        assert MF.list_fields(db_path=db) == []
        assert MF.delete_field(f["id"], db_path=db) is False  # повтор — False
    finally:
        Path(db).unlink(missing_ok=True)


def t_field_validation():
    db = _tmpdb()
    try:
        for bad in [dict(lat=49.9), dict(lat=54.1), dict(lon=64.9),
                    dict(lon=72.1), dict(area_ha=0.5), dict(area_ha=2001)]:
            kw = dict(name="X", lat=51.9, lon=66.4, area_ha=100.0,
                      crop="barley")
            kw.update(bad)
            try:
                MF.add_field(db_path=db, **kw)  # type: ignore[arg-type]
            except ValueError:
                pass
            else:
                raise AssertionError(f"валидация пропустила {bad}")
        assert MF.list_fields(db_path=db) == []
    finally:
        Path(db).unlink(missing_ok=True)


def t_default_db_path():
    assert MF.DB_PATH.name == "myfields.db", MF.DB_PATH
    assert MF.DB_PATH.parent.name == "data", MF.DB_PATH
    assert J.DB_PATH == MF.DB_PATH, (J.DB_PATH, MF.DB_PATH)


# ------------------------------------------------------------- journal
def t_note_crud():
    db = _tmpdb()
    try:
        f = MF.add_field("Поле-Журнал", 52.0, 67.0, 50.0, "barley", db_path=db)
        n = J.add_note(f["id"], "weeds", "Осот по краю", db_path=db)
        assert isinstance(n.get("id"), int), n
        assert n["field_id"] == f["id"] and n["problem_type"] == "weeds", n
        assert len(n.get("date", "")) >= 8, n
        notes = J.list_notes(f["id"], db_path=db)
        assert len(notes) == 1 and notes[0]["text"].startswith("Осот"), notes
        n2 = J.add_note(f["id"], "drought", "Қуаңшылық белгілері",
                        date="2026-08-01", db_path=db)
        assert n2["date"] == "2026-08-01", n2
        assert len(J.list_notes(f["id"], db_path=db)) == 2
    finally:
        Path(db).unlink(missing_ok=True)


def t_note_validation():
    db = _tmpdb()
    try:
        f = MF.add_field("Поле-Вал", 52.0, 67.0, 10.0, "oats", db_path=db)
        for ptype, text, dt in [("alien", "x", None), ("weeds", "   ", None)]:
            try:
                J.add_note(f["id"], ptype, text, date=dt, db_path=db)
            except ValueError:
                pass
            else:
                raise AssertionError(f"валидация пропустила {ptype!r}/{text!r}")
        try:
            J.add_note(999999, "weeds", "нет такого поля", db_path=db)
        except ValueError:
            pass
        else:
            raise AssertionError("note к несуществующему полю прошла")
        # подписи типов RU/KZ/EN
        assert J.problem_label("weeds", "ru") == "Сорняки"
        assert J.problem_label("drought", "kz") == "Құрғақшылық"
        assert J.problem_label("pests", "en") == "Pests"
        assert set(J.PROBLEM_TYPES) == {"weeds", "pests", "disease",
                                        "lodging", "drought", "other"}
    finally:
        Path(db).unlink(missing_ok=True)


# --------------------------------------------------------------- spray
def t_spray_bad_district():
    try:
        SP.check_spray_window("NoSuchDistrict", hours=48)
    except ValueError:
        return
    raise AssertionError("неизвестный район не дал ValueError")


def t_spray_live_or_skip():
    try:
        res = SP.check_spray_window("Esil", hours=48)
    except RuntimeError as e:
        raise RuntimeError(f"SKIP-OFFLINE: Open-Meteo недоступен ({e})") from e
    assert res["district_en"] == "Esil", res
    assert res["hours_checked"] >= 1, res
    assert isinstance(res["next_good_hours"], list), res
    for h in res["next_good_hours"]:
        assert set(("time", "temp_c", "wind_ms", "precip_mm")) <= set(h), h
        assert h["wind_ms"] < 5.0 and h["precip_mm"] == 0, h
        assert 10.0 <= h["temp_c"] <= 25.0, h
    for k in ("verdict_ru", "verdict_kz", "verdict_en"):
        assert isinstance(res.get(k), str) and len(res[k]) > 10, (k, res.get(k))
    print("  spray verdict RU:", res["verdict_ru"])
    print("  spray verdict KZ:", res["verdict_kz"])
    print("  spray verdict EN:", res["verdict_en"])
    print(f"  good {res['good_count']}/{res['hours_checked']}")


# --------------------------------------------------------------- router
def t_router():
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.platform_api import router
    except Exception as e:
        raise RuntimeError(f"SKIP-OFFLINE: TestClient/router недоступен ({e})") from e
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    r = c.get("/myfields")
    assert r.status_code == 200, r.text
    assert "fields" in r.json(), r.text

    r = c.post("/myfields", json={"name": "", "lat": 51.9, "lon": 66.4,
                                  "area_ha": 10, "crop": "barley"})
    assert r.status_code == 422, r.text

    r = c.post("/myfields", json={"name": "АПИ-Тест-Поле", "lat": 51.9,
                                  "lon": 66.4, "area_ha": 10,
                                  "crop": "barley"})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    try:
        r = c.get("/journal", params={"field_id": fid})
        assert r.status_code == 200 and r.json()["count"] == 0, r.text
        r = c.post("/journal", json={"field_id": fid, "problem_type": "pests",
                                     "text": "Тля на флаговом листе"})
        assert r.status_code == 201, r.text
        r = c.get("/journal", params={"field_id": fid})
        assert r.status_code == 200 and r.json()["count"] == 1, r.text
        r = c.post("/journal", json={"field_id": fid, "problem_type": "alien",
                                     "text": "x"})
        assert r.status_code == 422, r.text
    finally:
        import sqlite3 as _sq
        _con = _sq.connect(str(MF.DB_PATH))
        try:
            _con.execute("DELETE FROM notes WHERE field_id = ?", (fid,))
            _con.commit()
        finally:
            _con.close()
        MF.delete_field(fid)  # чистка дефолтной БД после API-теста

    r = c.get("/spray", params={"district_en": "Esil"})
    if r.status_code == 502:
        print("  spray via API: SKIP (offline):", r.json())
    else:
        assert r.status_code == 200, r.text
        assert "verdict_ru" in r.json(), r.text
    r = c.get("/spray", params={"district_en": "NoSuch"})
    assert r.status_code == 422, r.text


if __name__ == "__main__":
    check("myfields add/list/delete", t_field_crud)
    check("myfields validation Akmola", t_field_validation)
    check("default DB path data/myfields.db", t_default_db_path)
    check("journal add/list", t_note_crud)
    check("journal validation + labels", t_note_validation)
    check("spray bad district ValueError", t_spray_bad_district)
    check("spray live 48h Esil (or offline skip)", t_spray_live_or_skip)
    check("platform_api router", t_router)
    print(f"\nOK: {len(passed)} passed, {len(skipped)} skipped"
          + (f" ({', '.join(skipped)})" if skipped else ""))
