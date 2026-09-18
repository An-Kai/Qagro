"""fields_osm.py — реальные оцифрованные поля Акмолы через Overpass API.

Источники:
  - OpenStreetMap via Overpass API https://overpass-api.de/api/interpreter
    (лицензия данных OSM: ODbL https://www.openstreetmap.org/copyright)
  - Запасной дамп Geofabrik Kazakhstan
    https://download.geofabrik.de/asia/kazakhstan.html (ODbL)
  - Официальный источник для пилота: map.iaqmola.kz (Smart GeoHub,
    требует авторизации — см. data/fields/FIELDS_README.md)

Методика (см. FIELDS_README.md):
  Для каждого райцентра из config/districts.yaml запрашивается
  landuse=farmland в радиусе 15000 м, лимит 15 полигонов на район,
  timeout 60 c. Площадь area_ha — haversine approx (equirectangular
  проекция + формула шнурка). Если Overpass вернул 0 полигонов или
  ошибку — генерируются 3 честных демо-прямоугольника 1x2 км
  (200 га) с флагом demo:true (НЕ выдаются за OSM).

Выход: data/fields/akmola_osm_fields.geojson
  Polygon/MultiPolygon, properties: district_en, area_ha, source.

Запуск (Windows PowerShell):
  pip install requests pyyaml
  python src/fields_osm.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import requests

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "districts.yaml"
OUT_DIR = ROOT / "data" / "fields"
OUT_GEOJSON = OUT_DIR / "akmola_osm_fields.geojson"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RADIUS_M = 15000
LIMIT_PER_DISTRICT = 15
OVERPASS_TIMEOUT_S = 60
REQUEST_TIMEOUT_S = 75
SLEEP_BETWEEN_S = 2.0

EARTH_R_M = 6371000.0


# ---------------------------------------------------------------- geo helpers
def ring_area_ha(ring_lonlat: list) -> float:
    """Площадь кольца [(lon,lat),...] в га, equirectangular approx.

    x = lon_rad * R * cos(lat0), y = lat_rad * R, далее шнурок.
    Достаточно точно для полей ~км на широтах Акмолы (~51-53N).
    """
    if len(ring_lonlat) < 4:
        return 0.0
    lat0 = math.radians(sum(p[1] for p in ring_lonlat) / len(ring_lonlat))
    cos0 = math.cos(lat0)
    xy = [(math.radians(lon) * EARTH_R_M * cos0,
           math.radians(lat) * EARTH_R_M) for lon, lat in ring_lonlat]
    s = 0.0
    for i in range(len(xy) - 1):
        s += xy[i][0] * xy[i + 1][1] - xy[i + 1][0] * xy[i][1]
    return abs(s) / 2.0 / 10000.0


def geom_area_ha(geom: dict) -> float:
    t = geom.get("type")
    try:
        if t == "Polygon":
            return sum(ring_area_ha(r) for r in geom.get("coordinates", []))
        if t == "MultiPolygon":
            return sum(ring_area_ha(r)
                       for poly in geom.get("coordinates", [])
                       for r in poly)
    except Exception:
        return 0.0
    return 0.0


def close_ring(lonlat: list) -> list:
    if lonlat and lonlat[0] != lonlat[-1]:
        lonlat = lonlat + [lonlat[0]]
    return lonlat


# ---------------------------------------------------------------- overpass
def build_query(lat: float, lon: float) -> str:
    return (
        f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];"
        f"(nwr[\"landuse\"=\"farmland\"](around:{RADIUS_M},{lat},{lon}););"
        f"out geom {LIMIT_PER_DISTRICT};"
    )


def element_to_features(el: dict, district_en: str,
                        district_ru: str) -> list[dict]:
    """Way/relation Overpass -> 0..N GeoJSON features (лимит режется выше)."""
    feats: list[dict] = []
    typ = el.get("type")
    oid = el.get("id")
    tags = el.get("tags", {}) or {}
    name = tags.get("name")

    if typ == "way":
        geom = el.get("geometry") or []
        if len(geom) < 4:
            return []
        ring = close_ring([[p["lon"], p["lat"]] for p in geom])
        g = {"type": "Polygon", "coordinates": [ring]}
        feats.append({
            "type": "Feature",
            "geometry": g,
            "properties": {
                "district_en": district_en,
                "district_ru": district_ru,
                "area_ha": round(geom_area_ha(g), 2),
                "source": "OSM ODbL",
                "demo": False,
                "osm_type": "way",
                "osm_id": oid,
                "osm_name": name,
            },
        })
    elif typ == "relation":
        polys: list[list] = []
        for m in el.get("members", []) or []:
            if m.get("type") != "way":
                continue
            role = m.get("role", "")
            if role not in ("", "outer"):
                continue  # inner-кольца пропускаем на MVP
            mg = m.get("geometry") or []
            if len(mg) < 4:
                continue
            polys.append([close_ring([[p["lon"], p["lat"]] for p in mg])])
            if len(polys) >= LIMIT_PER_DISTRICT:
                break
        if not polys:
            return []
        if len(polys) == 1:
            g = {"type": "Polygon", "coordinates": polys[0]}
        else:
            g = {"type": "MultiPolygon", "coordinates": polys}
        feats.append({
            "type": "Feature",
            "geometry": g,
            "properties": {
                "district_en": district_en,
                "district_ru": district_ru,
                "area_ha": round(geom_area_ha(g), 2),
                "source": "OSM ODbL",
                "demo": False,
                "osm_type": "relation",
                "osm_id": oid,
                "osm_name": name,
            },
        })
    return feats  # nodes игнорируем: нужны только полигоны


def fetch_district(session: requests.Session, lat: float, lon: float,
                   district_en: str, district_ru: str) -> tuple[list[dict], str]:
    """Запрос Overpass по району. Возвращает (features, status)."""
    q = build_query(lat, lon)
    try:
        r = session.post(OVERPASS_URL, data={"data": q},
                         timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [], f"error: {type(e).__name__}: {e}"
    feats: list[dict] = []
    for el in data.get("elements", []) or []:
        if len(feats) >= LIMIT_PER_DISTRICT:
            break
        try:
            feats.extend(element_to_features(el, district_en, district_ru))
        except Exception:
            continue
        feats = feats[:LIMIT_PER_DISTRICT]
    # отсев вырожденных
    feats = [f for f in feats
             if f["geometry"]["type"] in ("Polygon", "MultiPolygon")
             and f["properties"]["area_ha"] > 0]
    if not feats:
        return [], "empty: Overpass вернул 0 полигонов"
    return feats, f"ok: {len(feats)} OSM-полигонов"


# ---------------------------------------------------------------- demo fallback
def demo_rectangles(lat: float, lon: float, district_en: str,
                    district_ru: str) -> list[dict]:
    """3 честных демо-прямоугольника 1x2 км (~200 га) вокруг центра.

    Смещения центров (км): (-4,-3), (2,2), (5,-2) — чтобы не налезали.
    Флаг demo:true, source='demo-fallback' — НЕ OSM, см. README.
    """
    cos0 = math.cos(math.radians(lat))
    feats = []
    for i, (dlat_km, dlon_km) in enumerate([(-4.0, -3.0),
                                           (2.0, 2.0), (5.0, -2.0)]):
        clat = lat + dlat_km / 111.32
        clon = lon + dlon_km / (111.32 * cos0)
        h_lat = 0.5 / 111.32
        h_lon = 1.0 / (111.32 * cos0)
        ring = close_ring([
            [clon - h_lon, clat - h_lat],
            [clon + h_lon, clat - h_lat],
            [clon + h_lon, clat + h_lat],
            [clon - h_lon, clat + h_lat],
        ])
        g = {"type": "Polygon", "coordinates": [ring]}
        feats.append({
            "type": "Feature",
            "geometry": g,
            "properties": {
                "district_en": district_en,
                "district_ru": district_ru,
                "area_ha": round(geom_area_ha(g), 2),
                "source": "demo-fallback",
                "demo": True,
                "note": ("Демо-прямоугольник 1x2 км: Overpass вернул 0/ошибку, "
                         "не данные OSM."),
                "demo_id": f"{district_en}_demo_{i + 1}",
            },
        })
    return feats


# ---------------------------------------------------------------- main
def load_districts() -> list[dict]:
    if yaml is None:
        raise RuntimeError("Нужен pyyaml: pip install pyyaml")
    with open(CFG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("districts", [])


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    districts = load_districts()
    session = requests.Session()
    session.headers.update({"User-Agent": "Qagro fields_osm v2 (hackathon MVP)"})

    all_feats: list[dict] = []
    n_real = n_demo = 0
    per_district: list[dict] = []

    for d in districts:
        en = d["name_en"]
        ru = d.get("name_ru", en)
        lat, lon = float(d["lat"]), float(d["lon"])
        print(f"[{en}] Overpass landuse=farmland around {lat},{lon} ...",
              flush=True)
        feats, status = fetch_district(session, lat, lon, en, ru)
        if feats:
            all_feats.extend(feats)
            n_real += len(feats)
        else:
            print(f"  -> {status}; генерирую 3 демо-прямоугольника.",
                  flush=True)
            demo = demo_rectangles(lat, lon, en, ru)
            all_feats.extend(demo)
            n_demo += len(demo)
            status += " -> 3 demo 1x2km"
        per_district.append({"district_en": en, "status": status})
        time.sleep(SLEEP_BETWEEN_S)

    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "method": (f"Overpass landuse=farmland, radius {RADIUS_M} m, "
                       f"limit {LIMIT_PER_DISTRICT}/district, "
                       f"timeout {OVERPASS_TIMEOUT_S}s"),
            "overpass": OVERPASS_URL,
            "license": "OSM data ODbL; demo features are NOT OSM",
            "n_osm": n_real,
            "n_demo": n_demo,
            "per_district": per_district,
        },
        "features": all_feats,
    }
    OUT_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False),
                           encoding="utf-8")
    print(f"\nСохранено: {OUT_GEOJSON}")
    print(f"Итого: {len(all_feats)} полигонов "
          f"(реальных OSM: {n_real}, demo: {n_demo})")
    for p in per_district:
        print(f"  {p['district_en']}: {p['status']}")
    if all_feats:
        f0 = all_feats[0]
        print("Пример:", json.dumps(
            {"geometry_type": f0["geometry"]["type"],
             "properties": f0["properties"]},
            ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
