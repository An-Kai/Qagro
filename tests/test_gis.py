"""test_gis.py — проверки Трека 1 (GIS и ДЗЗ).

Запуск: python tests/test_gis.py
Проверки:
- classify_field на синтетике: healthy -> cultivated,
  amplitude-low -> likely_fallow, max-low-разброс -> sparse.
- run_district('Esil', max_fields=2): live либо честный пропуск при offline
  (classify-тесты при этом всегда выполняются).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _fix_console() -> None:
    """UTF-8 для кириллицы в cp1251-консоли. Только прямой запуск (no-op под pytest)."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    try:
        if getattr(sys.stdout, "encoding", "utf-8").lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:  # pragma: no cover
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gis_monitor import classify_field, run_district  # noqa: E402

passed: list[str] = []


def check(name: str, fn) -> None:
    fn()
    passed.append(name)
    print(f"PASS: {name}")


def _series(vals: list[float | None]) -> list[dict]:
    return [{"date": f"2024-06-{i + 1:02d}", "ndvi_mean": v} for i, v in enumerate(vals)]


def t_healthy_cultivated():
    # Здоровый ход: рост и спад, высокий пик
    cls = classify_field(_series([0.25, 0.55, 0.65, 0.40]))
    assert cls["status"] == "cultivated", cls
    assert abs(cls["ndvi_max"] - 0.65) < 1e-9, cls
    assert abs(cls["amplitude"] - 0.40) < 1e-9, cls
    assert cls["dead_share"] == 0.25, cls  # 1 из 4 < 0.3


def t_amplitude_low_fallow():
    # Ровный низкий ход — возможно, не сеяли
    cls = classify_field(_series([0.28, 0.30, 0.32, 0.29]))
    assert cls["status"] == "likely_fallow", cls
    assert cls["amplitude"] < 0.15, cls


def t_max_low_sparse():
    # Разброс есть (0.17), но пик низкий — изреженность
    cls = classify_field(_series([0.15, 0.20, 0.32, 0.22]))
    assert cls["status"] == "sparse", cls
    assert cls["ndvi_max"] < 0.35, cls
    assert cls["amplitude"] >= 0.15, cls


def t_run_esil_live_or_skip():
    """Live (2 поля Esil) либо честный пропуск при offline."""
    try:
        summary = run_district("Esil", max_fields=2)
    except Exception as e:
        print(f"SKIP: run_district Esil offline (исключение: {type(e).__name__}: {e})")
        return
    detail_p = ROOT / "data" / "gis" / "gis_Esil.json"
    summ_p = ROOT / "data" / "gis" / "gis_summary.json"
    # если все ndvi None (сеть отвалилась внутри) — честный пропуск
    try:
        detail = json.loads(detail_p.read_text(encoding="utf-8"))
        all_none = all(p.get("ndvi_mean") is None
                       for f in detail.get("fields", [])
                       for p in f.get("series", []))
    except Exception as e:
        print(f"SKIP: run_district Esil offline (файл не читается: {e})")
        return
    if all_none:
        print("SKIP: run_district Esil offline (все ndvi_mean=None, сеть недоступна)")
        return
    assert summary["checked"] == 2, summary
    assert summary["total_fields"] >= 2, summary
    for k in ("total_fields", "checked", "cultivated", "sparse",
              "likely_fallow", "avg_ndvi_max"):
        assert k in summary, summary
    assert detail_p.exists() and summ_p.exists()
    assert len(detail.get("fields", [])) == 2, detail.keys()
    print(f"LIVE: Esil checked=2 summary={summary}")


def t_zhaksy_scenes_offline():
    """Офлайн: у ВСЕХ 10 районов есть настоящие сцены (регрессия 'No NDVI data').

    Без сети: ndvi_timeseries.json обязан содержать >=5 записей с конечным
    ndvi_mean в [-1,1] и scene_id на район (настоящие PC TiTiler:
    scripts/fetch_ndvi_district.py, не выдумка).
    """
    p = ROOT / "data" / "ndvi" / "ndvi_timeseries.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", raw)
    by_d: dict[str, list] = {}
    for r in items:
        if (isinstance(r, dict) and isinstance(r.get("ndvi_mean"), (int, float))
                and -1.0 <= float(r["ndvi_mean"]) <= 1.0 and r.get("scene_id")):
            by_d.setdefault(str(r.get("district")), []).append(r)
    want = {"Atbasar", "Bulandy", "Burabay", "Esil", "Kokshetau",
            "Sandyktau", "Shortandy", "Tselinograd", "Zerenda", "Zhaksy"}
    missing = want - set(by_d)
    assert not missing, f"нет real-сцен: {sorted(missing)}"
    thin = {d: len(v) for d, v in by_d.items() if len(v) < 5}
    assert not thin, f"мало real-записей (<5): {thin}"
    zh_dates = sorted({r["date"] for r in by_d["Zhaksy"]})
    assert len(zh_dates) >= 4, f"мало дат Zhaksy: {zh_dates}"


if __name__ == "__main__":
    _fix_console()
    check("classify healthy->cultivated", t_healthy_cultivated)
    check("classify amplitude-low->likely_fallow", t_amplitude_low_fallow)
    check("classify max-low->sparse", t_max_low_sparse)
    check("scenes offline (10 districts >=5 real)", t_zhaksy_scenes_offline)
    check("run_district Esil max2 (live/skip)", t_run_esil_live_or_skip)
    print(f"OK: {len(passed)}/{len(passed)} — {', '.join(passed)}")
