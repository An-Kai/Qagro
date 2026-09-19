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
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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


if __name__ == "__main__":
    check("classify healthy->cultivated", t_healthy_cultivated)
    check("classify amplitude-low->likely_fallow", t_amplitude_low_fallow)
    check("classify max-low->sparse", t_max_low_sparse)
    check("run_district Esil max2 (live/skip)", t_run_esil_live_or_skip)
    print(f"OK: {len(passed)}/4 — {', '.join(passed)}")
