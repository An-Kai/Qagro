"""test_pytest_live.py — opt-in live-тесты (только --run-live).

Реальная сеть (Open-Meteo/TiTiler/AgroData), общий timeout через
conftest.run_bounded, записи — только в tmp_gis/tmp_db (tracked дерево
не трогаем). Сетевой провал -> pytest.skip, а не FAIL. Без флага файл
собирает 0 тестов (pytest.ini: -m "not live").
"""
from __future__ import annotations

import pytest

from conftest import run_bounded  # локальный tests/conftest.py (не site-packages)


@pytest.mark.live
def test_live_gis_esil(tmp_gis):
    from src.gis_monitor import run_district

    try:
        s = run_bounded(lambda: run_district("Esil", max_fields=1), timeout=180.0)
    except Exception as e:
        pytest.skip(f"live GIS недоступен: {type(e).__name__}: {e}")
    assert s["checked"] == 1
    assert (tmp_gis / "gis_Esil.json").exists()


@pytest.mark.live
def test_live_spray():
    from src.spray import check_spray_window

    try:
        r = run_bounded(lambda: check_spray_window("Esil", 48), timeout=60.0)
    except Exception as e:
        pytest.skip(f"live Open-Meteo недоступен: {type(e).__name__}: {e}")
    assert r["good_count"] >= 0 and "verdict_ru" in r


@pytest.mark.live
def test_live_agrodata():
    from src.fetch_agrodata import compare_agrodata

    try:
        out = run_bounded(lambda: compare_agrodata("Esil", {"y_pred": 11.0}, "ru"),
                          timeout=120.0)
    except Exception as e:
        pytest.skip(f"live AgroData недоступен: {type(e).__name__}: {e}")
    assert out["district_en"] == "Esil" and "agreement" in out
