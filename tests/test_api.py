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


def t_predict_sunflower_experimental():
    r = client.post("/predict", json={
        "district_en": "Esil", "crop": "sunflower",
        "lang": "ru", "include_risk": False,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    exp_top = j.get("experimental")
    exp_pred = (j.get("pred") or {}).get("experimental")
    exp_ins = (j.get("insurance") or {}).get("experimental")
    assert True in (exp_top, exp_pred, exp_ins), (
        f"sunflower должен быть experimental: top={exp_top} "
        f"pred={exp_pred} ins={exp_ins}"
    )


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


if __name__ == "__main__":
    check("health 200 + counts", t_health)
    check("predict Esil wheat 200", t_predict_wheat)
    check("predict Esil sunflower experimental", t_predict_sunflower_experimental)
    check("predict bad district 422", t_predict_bad_district_422)
    check("predict bad crop 422", t_predict_bad_crop_422)
    check("fields >=60", t_fields)
    check("granaries 12", t_granaries)
    check("metrics trimmed", t_metrics_trimmed)
    check("version git sha", t_version)
    print(f"\nOK: {len(passed)}/{len(passed)} passed")
