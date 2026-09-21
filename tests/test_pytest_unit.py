"""test_pytest_unit.py — offline unit-тесты для `python -m pytest -q`.

Без сети (моки stdlib unittest.mock), без записи в трекаемые файлы репо,
без sys.stdout-хаков (capture pytest — UTF-8). Дублирует ключевые проверки
standalone-скриптов в pytest-форме, скрипты при этом не трогаем.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.gis_monitor import _district_dates, classify_field, field_bbox, run_district


def _series(vals):
    return [{"date": f"2024-06-{i + 1:02d}", "ndvi_mean": v}
            for i, v in enumerate(vals)]


@pytest.mark.unit
def test_classify_cultivated():
    cls = classify_field(_series([0.25, 0.55, 0.65, 0.40]))
    assert cls["status"] == "cultivated" and cls["ndvi_max"] == 0.65


@pytest.mark.unit
def test_classify_fallow_and_sparse():
    assert classify_field(_series([0.28, 0.30, 0.32, 0.29]))["status"] == "likely_fallow"
    assert classify_field(_series([0.15, 0.20, 0.32, 0.22]))["status"] == "sparse"
    assert classify_field(_series([None, None]))["status"] == "no_data"


@pytest.mark.unit
def test_fmt_window_single_and_range():
    from src.spray import _fmt_window, _windows

    assert "до 23:00" not in _fmt_window("2026-09-20T23:00", "2026-09-20T23:00", "ru")
    assert "at 23:00" in _fmt_window("2026-09-20T23:00", "2026-09-20T23:00", "en")
    wins = _windows(["2026-09-20T20:00", "2026-09-20T21:00", "2026-09-20T23:00"])
    assert wins == [("2026-09-20T20:00", "2026-09-20T21:00"),
                    ("2026-09-20T23:00", "2026-09-20T23:00")]


@pytest.mark.unit
def test_search_guide_complaints():
    from src.guide_data import search_guide, text_of

    assert search_guide("саранча", "ru")[0]["id"] == "pest_locust"
    assert search_guide("шегіртке", "kz")[0]["id"] == "pest_locust"
    assert search_guide("засуха", "ru")[0]["id"] == "abio_drought"
    assert search_guide("frost", "en")[0]["id"] == "abio_frost"
    assert search_guide("абракадабра", "ru") == []
    it = search_guide("ржавчина", "ru")[0]
    assert text_of(it, "names", "ru") and text_of(it, "signs", "ru")


@pytest.mark.unit
def test_field_bbox_synthetic():
    ring = [[66.0, 51.0], [66.5, 51.0], [66.5, 51.5], [66.0, 51.5], [66.0, 51.0]]
    field = {"geometry": {"type": "Polygon", "coordinates": [ring]}}
    bbox, squeezed = field_bbox(field)
    assert squeezed is True
    assert bbox[2] - bbox[0] <= 0.021 and bbox[3] - bbox[1] <= 0.021  # float-пыль 0.02


@pytest.mark.unit
def test_district_dates_union():
    dates = _district_dates("Esil")
    assert "2024-06-03" in dates  # DEFAULT
    zh = _district_dates("Zhaksy")
    assert len(zh) > 6  # DEFAULT + сцены района


@pytest.mark.unit
def test_interval_coverage_present():
    from src.api import _interval_coverage

    assert _interval_coverage("spring_wheat") == 0.66
    assert _interval_coverage("rapeseed") == 0.04
    assert _interval_coverage("no_such_crop") is None


@pytest.mark.unit
def test_spray_verdict_mocked():
    from datetime import datetime, timedelta

    from src import spray as SP

    base = datetime.now().replace(minute=0, second=0, microsecond=0)
    times = [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
    hourly = {
        "time": times,
        "temperature_2m": [18.0] * 48,
        "precipitation": [0.0] * 48,
        "wind_speed_10m": [2.0] * 48,
        "relative_humidity_2m": [50.0] * 48,
    }
    with patch.object(SP, "_fetch_hourly",
                       return_value={"hourly": hourly, "utc_offset_seconds": 21600}):
        r = SP.check_spray_window("Esil", 48)
    assert r["good_count"] == r["hours_checked"] > 0
    assert "хорошо" in r["verdict_ru"]


@pytest.mark.unit
def test_gis_series_mocked(tmp_gis):
    from src import gis_monitor as G

    with patch.object(G, "_titiler_ndvi", return_value=(0.55, "mocked")):
        s = G.run_district("Esil", max_fields=1)
    assert s["checked"] == 1
    # все даты 0.55 -> amplitude 0 -> likely_fallow (моки не меняют логику порогов)
    assert s["fields"][0]["classification"]["status"] == "likely_fallow"
    assert (tmp_gis / "gis_Esil.json").exists()  # пишет только в tmp


@pytest.mark.unit
def test_agrodata_mocked():
    from src import fetch_agrodata as FA

    towns = [{"town": {"nameRu": "Есиль", "nameKk": "Есіл",
                       "district": {"nameRu": "Есильский",
                                    "region": {"nameRu": "Акмолинская область"}}},
              "value": -0.14, "modified": "2026-08-05"}]
    prods = [{"nameRu": "Есильский", "nameKk": "Есіл",
              "valueFrom": 9.3, "valueTo": 11.3, "color": "Middle"}]
    with patch.object(FA, "_get_json", side_effect=[towns, prods]):
        out = FA.compare_agrodata("Esil", {"y_pred": 10.5}, "ru")
    assert out["drought"]["count"] == 1 and out["productivity"]["count"] == 1
    assert "10.5" in out["agreement"]


@pytest.mark.unit
def test_myfields_tmp_db(tmp_db):
    from src import myfields as MF

    assert str(tmp_db).startswith(str(tmp_db.parent))
    rec = MF.add_field("Юнит-Поле", 51.95, 66.40, 10.0, "spring_wheat")
    rows = MF.list_fields()
    assert any(r["id"] == rec["id"] for r in rows)
    assert tmp_db.exists()


@pytest.mark.unit
def test_production_cors_failfast(monkeypatch):
    import importlib

    import src.api as api_mod

    monkeypatch.setenv("QAGRO_ENV", "production")
    monkeypatch.delenv("QAGRO_CORS_ORIGINS", raising=False)
    with pytest.raises(RuntimeError):
        importlib.reload(api_mod)
    monkeypatch.setenv("QAGRO_ENV", "local")
    importlib.reload(api_mod)
