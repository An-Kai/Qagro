"""logistics.py — ближайший элеватор к району (haversine).

Данные: data/fields/granaries.json (12 элеваторов Акмолы,
координаты оценочные по Qoldau granaries-map, см. файл).
Райцентры: config/districts.yaml.

nearest_elevator(district_en) -> {name, name_ru, dist_km, lat, lon, ...}
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRANARIES_JSON = ROOT / "data" / "fields" / "granaries.json"
CFG = ROOT / "config" / "districts.yaml"

EARTH_R_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_granaries() -> list[dict]:
    with open(GRANARIES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("granaries", data) if isinstance(data, dict) else data
    return items


@lru_cache(maxsize=1)
def load_districts() -> dict[str, dict]:
    import yaml

    with open(CFG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {d["name_en"]: d for d in cfg.get("districts", [])}


def nearest_elevator(district_en: str) -> dict:
    """Ближайший элеватор к райцентру district_en.

    Возвращает {name, name_ru, dist_km, lat, lon, id, district_en, estimated}.
    """
    districts = load_districts()
    if district_en not in districts:
        raise ValueError(f"district_en={district_en!r} нет в districts.yaml. "
                         f"Допустимо: {sorted(districts)}")
    d = districts[district_en]
    lat, lon = float(d["lat"]), float(d["lon"])
    best: dict | None = None
    best_dist = float("inf")
    for g in load_granaries():
        dist = haversine_km(lat, lon, float(g["lat"]), float(g["lon"]))
        if dist < best_dist:
            best_dist = dist
            best = g
    assert best is not None
    return {
        "name": best.get("name_en", best.get("id")),
        "name_ru": best.get("name_ru"),
        "id": best.get("id"),
        "dist_km": round(best_dist, 1),
        "lat": best.get("lat"),
        "lon": best.get("lon"),
        "district_en": district_en,
        "estimated": bool(best.get("estimated", True)),
        "source": best.get("source", "qoldau granaries-map"),
    }


def all_distances(district_en: str) -> list[dict]:
    """Все элеваторы с дистанцией, по возрастанию (для отладки/UI)."""
    districts = load_districts()
    d = districts[district_en]
    lat, lon = float(d["lat"]), float(d["lon"])
    out = []
    for g in load_granaries():
        out.append({
            "name": g.get("name_en", g.get("id")),
            "name_ru": g.get("name_ru"),
            "dist_km": round(haversine_km(lat, lon, float(g["lat"]),
                                          float(g["lon"])), 1),
        })
    return sorted(out, key=lambda x: x["dist_km"])


if __name__ == "__main__":
    import sys

    arg = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    print(json.dumps(nearest_elevator(arg), ensure_ascii=False, indent=2))
