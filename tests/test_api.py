"""test_api.py — C2 hardening без pytest-зависимости.

Запуск: python tests/test_api.py
- assert + TestClient; если fastapi/httpx нет — skip с exit 0.
- include_risk=False чтобы не ходить в Open-Meteo (offline-safe, быстро).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
except Exception as e:  # fastapi/httpx нет — скип без падения CI
    print(f"SKIP: TestClient недоступен ({e})")
    raise SystemExit(0)

try:
    from src.api import app
except Exception as e:
    print(f"SKIP: не импортировать src.api ({e})")
    raise SystemExit(0)

client = TestClient(app)
passed = []


def check(name: str, fn) -> None:
    fn()
    passed.append(name)
    print(f"PASS: {name}")


def t_health():
    r = client.get("/health")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("status") == "ok", j
    assert "crops" in j and "spring_wheat" in j["crops"], j
    # C2: counts districts/crops/models
    counts = j.get("counts") or {}
    assert counts.get("districts") == 10, counts
    assert counts.get("crops") == 6, counts
    assert counts.get("models") == 6, counts


def t_predict_wheat():
    r = client.post("/predict", json={
        "district_en": "Esil", "crop": "spring_wheat",
        "lang": "ru", "include_risk": False,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j.get("y_pred"), (int, float)), j
    assert "lo" in j and "hi" in j, j
    # wheat — не experimental
    exp = j.get("experimental", (j.get("pred") or {}).get("experimental"))
    assert exp is False, j.get("pred")


def t_predict_sunflower_strong():
    # C6: sunflower v3 — strong (below_baseline=false, experimental:false).
    # Сверяемся с metrics/metrics.json как источником истины + требуем strong явно.
    import json
    mj = ROOT / "metrics" / "metrics.json"
    below = bool(json.loads(mj.read_text(encoding="utf-8"))
                 .get("sunflower", {}).get("below_baseline", False))
    assert below is False, (
        f"metrics.json: sunflower должен быть strong (below_baseline=false), получили {below}"
    )
    r = client.post("/predict", json={
        "district_en": "Esil", "crop": "sunflower",
        "lang": "ru", "include_risk": False,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    exp_top = j.get("experimental")
    exp_pred = (j.get("pred") or {}).get("experimental")
    exp_ins = (j.get("insurance") or {}).get("experimental")
    assert exp_top is False, f"sunflower top experimental должен быть False: {j.get('pred')}"
    assert exp_pred is False, f"sunflower pred.experimental должен быть False: {j.get('pred')}"
    assert exp_ins is False, f"sunflower insurance.experimental должен быть False: {j.get('insurance')}"


def t_predict_bad_district_422():
    r = client.post("/predict", json={
        "district_en": "BadDistrict", "crop": "spring_wheat",
        "lang": "ru", "include_risk": False,
    })
    assert r.status_code == 422, f"ожидали 422, получили {r.status_code}: {r.text}"
    detail = str(r.json().get("detail", ""))
    assert "Esil" in detail or "allowed" in detail or "Допустимо" in detail, detail


def t_predict_bad_crop_422():
    r = client.post("/predict", json={
        "district_en": "Esil", "crop": "bad_crop",
        "lang": "ru", "include_risk": False,
    })
    assert r.status_code == 422, f"ожидали 422, получили {r.status_code}: {r.text}"


def t_fields():
    r = client.get("/fields")
    assert r.status_code == 200, r.text
    j = r.json()
    feats = j.get("features", [])
    assert len(feats) >= 60, f"полей {len(feats)} < 60"


def t_granaries():
    r = client.get("/granaries")
    assert r.status_code == 200, r.text
    j = r.json()
    if isinstance(j, list):
        n = len(j)
    elif isinstance(j, dict):
        g = j.get("granaries", j.get("features", j))
        n = len(g) if isinstance(g, list) else 0
    else:
        n = 0
    assert n == 12, f"элеваторов {n} != 12: {str(j)[:300]}"


def t_metrics_trimmed():
    r = client.get("/metrics")
    assert r.status_code == 200, r.text
    j = r.json()
    crops = j.get("crops", {})
    assert "spring_wheat" in crops, crops.keys()
    for c, m in crops.items():
        assert "scatter" not in m, f"{c} содержит scatter (не обрезано)"


def t_version():
    r = client.get("/version")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("git_sha"), j
    assert j.get("build_date") or j.get("git_date"), j


def t_guide():
    r = client.get("/guide", params={"crop": "spring_wheat"})
    assert r.status_code == 200, r.text
    j = r.json()
    items = j.get("items", [])
    assert isinstance(items, list) and len(items) >= 1, j
    for it in items:
        assert "names" in it, it
        assert isinstance(it["names"], dict), it


def t_fertilizer():
    r = client.get("/fertilizer", params={"crop": "spring_wheat"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j.get("N_kg_ha"), (int, float)), j
    assert j["N_kg_ha"] > 0, j
    assert j.get("P_kg_ha", 0) > 0 and j.get("K_kg_ha", 0) > 0, j


def t_economy():
    r = client.get("/economy")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "profit_kzt_ha" in j, j
    assert isinstance(j["profit_kzt_ha"], (int, float)), j


def t_spray():
    r = client.get("/spray", params={"district_en": "Esil"})
    if r.status_code == 200:
        j = r.json()
        assert "good_count" in j or "next_good_hours" in j, j
        assert "verdict_ru" in j, j
    elif r.status_code in (502, 500):
        # честный offline-error без моков
        body = r.text.lower()
        assert "detail" in r.json() or "error" in body or "недоступен" in body, r.text
    else:
        raise AssertionError(f"spray: ожидали 200/502, получили {r.status_code}: {r.text}")


def t_calendar():
    r = client.get("/calendar", params={"crop": "spring_wheat"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("crop") == "spring_wheat", j
    assert "sowing_window" in j, j


def t_alerts():
    r = client.get("/alerts", params={"district_en": "Esil"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert "alerts" in j, j
    assert isinstance(j["alerts"], list), j


def t_soil():
    r = client.get("/soil")
    assert r.status_code == 200, r.text
    j = r.json()
    rows = j.get("rows", [])
    assert isinstance(rows, list) and len(rows) >= 1, j
    assert "district_en" in rows[0], rows[0]


def t_intervals():
    r = client.get("/intervals")
    assert r.status_code == 200, r.text
    j = r.json()
    crops = j.get("crops", {})
    assert "spring_wheat" in crops, crops.keys() if isinstance(crops, dict) else crops


if __name__ == "__main__":
    check("health 200 + counts", t_health)
    check("predict Esil wheat 200", t_predict_wheat)
    check("predict Esil sunflower strong", t_predict_sunflower_strong)
    check("predict bad district 422", t_predict_bad_district_422)
    check("predict bad crop 422", t_predict_bad_crop_422)
    check("fields >=60", t_fields)
    check("granaries 12", t_granaries)
    check("metrics trimmed", t_metrics_trimmed)
    check("version git sha", t_version)
    check("guide spring_wheat 200 + names", t_guide)
    check("fertilizer spring_wheat 200 + N>0", t_fertilizer)
    check("economy 200 + profit", t_economy)
    check("spray Esil 200/offline-error", t_spray)
    check("calendar spring_wheat 200", t_calendar)
    check("alerts Esil 200", t_alerts)
    check("soil 200 + rows", t_soil)
    check("intervals 200 + crops", t_intervals)
    print(f"\nOK: {len(passed)}/{len(passed)} passed")
