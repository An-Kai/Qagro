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

# C6: rotate зеркал + backoff против 429/504
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.net.tw/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",  # alias .org.tw (DNS-фолбэк)
]
OVERPASS_URL = OVERPASS_MIRRORS[0]  # дефолт, для metadata/back-compat
RADIUS_M = 15000
RADIUS_FALLBACK_M = 10000  # C6: меньший радиус для перегруженных районов
LIMIT_PER_DISTRICT = 15
OVERPASS_TIMEOUT_S = 60
REQUEST_TIMEOUT_S = 75
SLEEP_BETWEEN_S = 5.0  # C6: пауза между районами (было 2.0)
RETRY_SLEEPS_S = (15, 30, 60)  # C6: backoff 3 попытки
MAX_ATTEMPTS = 3
USER_AGENT = "QagroHackathon/1.0 (Akmola fields refill; hackathon MVP)"

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
def build_query(lat: float, lon: float,
                radius_m: int = RADIUS_M) -> str:
    return (
        f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];"
        f"(nwr[\"landuse\"=\"farmland\"](around:{radius_m},{lat},{lon}););"
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
    """Запрос Overpass по району с retry/backoff и ротацией зеркал (C6).

    Попытки: MAX_ATTEMPTS=3, паузы RETRY_SLEEPS_S=(15,30,60).
    Зеркала по кругу: overpass-api.de -> overpass.kumi.systems
      -> overpass.nchc.org.tw.
    Первая попытка — радиус RADIUS_M (15000), повторы — уменьшенный
    RADIUS_FALLBACK_M (10000) для перегруженных районов.
    Возвращает (features, status).
    """
    last_err = ""
    last_mirror = OVERPASS_MIRRORS[0]
    for attempt in range(MAX_ATTEMPTS):
        mirror = OVERPASS_MIRRORS[attempt % len(OVERPASS_MIRRORS)]
        last_mirror = mirror
        # C6: повторные попытки — меньший радиус
        radius = RADIUS_M if attempt == 0 else RADIUS_FALLBACK_M
        q = build_query(lat, lon, radius_m=radius)
        try:
            r = session.post(mirror, data={"data": q},
                             timeout=REQUEST_TIMEOUT_S)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            last_err = (f"attempt {attempt + 1}/{MAX_ATTEMPTS} "
                        f"mirror {mirror} radius {radius}: "
                        f"{type(e).__name__}: {e}")
            print(f"  -> {last_err}", flush=True)
            if attempt < MAX_ATTEMPTS - 1:
                wait = RETRY_SLEEPS_S[attempt] if attempt < len(RETRY_SLEEPS_S) else 60
                print(f"     backoff sleep {wait}s ...", flush=True)
                time.sleep(wait)
                continue
            return [], f"error: {last_err}"
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
        if feats:
            note = (f"ok: {len(feats)} OSM-полигонов "
                    f"(attempt {attempt + 1}, {mirror}, r={radius})")
            return feats, note
        # пустой ответ — тоже повод для retry меньшим радиусом
        # (иногда помогает при таймаутах сервера с усечением),
        # но чаще это реально отсутствие farmland.
        last_err = (f"attempt {attempt + 1}/{MAX_ATTEMPTS} mirror {mirror} "
                    f"radius {radius}: empty: Overpass вернул 0 полигонов")
        print(f"  -> {last_err}", flush=True)
        if attempt < MAX_ATTEMPTS - 1:
            wait = RETRY_SLEEPS_S[attempt] if attempt < len(RETRY_SLEEPS_S) else 60
            print(f"     backoff sleep {wait}s ...", flush=True)
            time.sleep(wait)
            continue
        return [], f"empty: Overpass вернул 0 полигонов после {MAX_ATTEMPTS} попыток (last mirror {last_mirror})"
    return [], f"error: {last_err}"


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


def main(argv: list[str] | None = None) -> int:
    import argparse
    import shutil
    from datetime import datetime, timezone

    ap = argparse.ArgumentParser(
        description="C6: добор полей с backoff (селективно по районам).")
    ap.add_argument("--only", default="",
                    help="Comma-separated district_en, напр. Atbasar,Esil")
    ap.add_argument("--refill", action="store_true",
                    help="Селективный добор: дозагрузить только --only, "
                         "остальные фичи оставить из существующего geojson.")
    ap.add_argument("--out", default=str(OUT_GEOJSON),
                    help="Куда писать результат")
    args = ap.parse_args(argv)

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    only_set = set(only)
    refill_mode = bool(args.refill and only)
    out_path = Path(args.out)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    districts = load_districts()
    if only_set:
        districts_todo = [d for d in districts if d["name_en"] in only_set]
        unknown = only_set - {d["name_en"] for d in districts}
        if unknown:
            print(f"WARN: неизвестные районы в --only: {sorted(unknown)}",
                  flush=True)
        if not districts_todo:
            print("ERROR: --only не совпал ни с одним районом.", flush=True)
            return 2
    else:
        districts_todo = districts

    # C6 бэкап существующего geojson перед записью
    old_fc: dict | None = None
    if out_path.exists():
        try:
            old_fc = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN: не смог прочитать старый geojson: {e}", flush=True)
            old_fc = None

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    if refill_mode and old_fc is not None:
        # Селективно: сохраняем фичи нетронутых районов как есть
        kept = [f for f in (old_fc.get("features") or [])
                if f.get("properties", {}).get("district_en") not in only_set]
        old_per = {p.get("district_en"): p.get("status", "")
                   for p in (old_fc.get("metadata", {}).get("per_district", []) or [])}
    else:
        kept = []
        old_per = {}
        if refill_mode and old_fc is None:
            print("WARN: --refill без существующего geojson: работаю как полный прогон по --only.",
                  flush=True)
            refill_mode = False

    all_feats: list[dict] = []
    n_real = n_demo = 0
    per_district_new: list[dict] = []

    for d in districts_todo:
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
            # C6 refill: при неудаче оставляем старые фичи района (демо),
            # а не генерируем новые дубликаты
            if refill_mode and old_fc is not None:
                old_feats = [f for f in (old_fc.get("features") or [])
                             if f.get("properties", {}).get("district_en") == en]
                if old_feats:
                    print(f"  -> {status}; оставляю {len(old_feats)} старых фич {en} (rate-limited).",
                          flush=True)
                    all_feats.extend(old_feats)
                    for f in old_feats:
                        if f.get("properties", {}).get("demo"):
                            n_demo += 1
                        else:
                            n_real += 1
                    status += " -> kept old features (rate-limited)"
                else:
                    print(f"  -> {status}; генерирую 3 демо-прямоугольника.",
                          flush=True)
                    demo = demo_rectangles(lat, lon, en, ru)
                    all_feats.extend(demo)
                    n_demo += len(demo)
                    status += " -> 3 demo 1x2km"
            else:
                print(f"  -> {status}; генерирую 3 демо-прямоугольника.",
                      flush=True)
                demo = demo_rectangles(lat, lon, en, ru)
                all_feats.extend(demo)
                n_demo += len(demo)
                status += " -> 3 demo 1x2km"
        per_district_new.append({"district_en": en, "status": status})
        time.sleep(SLEEP_BETWEEN_S)

    if refill_mode and old_fc is not None:
        final_feats = kept + all_feats
        # per_district: старые статусы нетронутых + новые по тронутым
        new_map = {p["district_en"]: p["status"] for p in per_district_new}
        old_list = old_fc.get("metadata", {}).get("per_district", []) or []
        merged_per: list[dict] = []
        for p in old_list:
            en = p.get("district_en")
            if en in new_map:
                merged_per.append({"district_en": en, "status": new_map[en]})
            else:
                merged_per.append(p)
        # районы из --only, которых не было в старом metadata (на всякий)
        known = {p["district_en"] for p in merged_per}
        for p in per_district_new:
            if p["district_en"] not in known:
                merged_per.append(p)
        per_district = merged_per
        n_osm = sum(1 for f in final_feats if not f.get("properties", {}).get("demo"))
        n_demo_tot = sum(1 for f in final_feats if f.get("properties", {}).get("demo"))
        refilled_ok = sum(1 for p in per_district_new if p["status"].startswith("ok:"))
        rate_limited = refilled_ok < len(per_district_new)
        old_meta = old_fc.get("metadata", {}) or {}
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata = {
            **old_meta,
            "method": (f"Overpass landuse=farmland, radius {RADIUS_M} m "
                       f"(fallback {RADIUS_FALLBACK_M} m on retry), "
                       f"limit {LIMIT_PER_DISTRICT}/district, "
                       f"timeout {OVERPASS_TIMEOUT_S}s; "
                       f"C6 refill backoff {list(RETRY_SLEEPS_S)}s, "
                       f"mirrors {len(OVERPASS_MIRRORS)}, sleep {SLEEP_BETWEEN_S}s"),
            "overpass": OVERPASS_URL,
            "overpass_mirrors": OVERPASS_MIRRORS,
            "license": "OSM data ODbL; demo features are NOT OSM",
            "n_osm": n_osm,
            "n_demo": n_demo_tot,
            "per_district": per_district,
            "c6_refill": {
                "targets": sorted(only_set),
                "refilled_ok": refilled_ok,
                "refilled_total": len(per_district_new),
                "updated_utc": ts,
                "rate_limited": rate_limited,
                "note": ("Частичный добор C6: обновлены только районы из targets; "
                         "остальные оставлены без изменений."
                         if refilled_ok else
                         "Добор C6 не удался (429/504): фичи оставлены как есть, "
                         "статусы попыток записаны в per_district (rate-limited)."),
            },
        }
        if rate_limited:
            metadata["rate_limited"] = True
    else:
        final_feats = all_feats
        n_osm, n_demo_tot = n_real, n_demo
        per_district = per_district_new
        metadata = {
            "method": (f"Overpass landuse=farmland, radius {RADIUS_M} m "
                       f"(fallback {RADIUS_FALLBACK_M} m on retry), "
                       f"limit {LIMIT_PER_DISTRICT}/district, "
                       f"timeout {OVERPASS_TIMEOUT_S}s; "
                       f"backoff {list(RETRY_SLEEPS_S)}s, sleep {SLEEP_BETWEEN_S}s"),
            "overpass": OVERPASS_URL,
            "overpass_mirrors": OVERPASS_MIRRORS,
            "license": "OSM data ODbL; demo features are NOT OSM",
            "n_osm": n_osm,
            "n_demo": n_demo_tot,
            "per_district": per_district,
        }

    fc = {
        "type": "FeatureCollection",
        "metadata": metadata,
        "features": final_feats,
    }
    # C6: бэкап старого файла рядом перед перезаписью
    if out_path.exists():
        ts_local = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = out_path.with_name(out_path.stem + f".backup_C6_{ts_local}.geojson")
        bak_simple = out_path.with_name(out_path.stem + ".backup_C6.geojson")
        try:
            shutil.copyfile(out_path, bak)
            shutil.copyfile(out_path, bak_simple)
            print(f"Бэкап: {bak.name} + {bak_simple.name}", flush=True)
        except Exception as e:
            print(f"WARN: бэкап не удался: {e}", flush=True)
    out_path.write_text(json.dumps(fc, ensure_ascii=False),
                        encoding="utf-8")
    print(f"\nСохранено: {out_path}")
    print(f"Итого: {len(final_feats)} полигонов "
          f"(реальных OSM: {n_osm}, demo: {n_demo_tot})")
    for p in per_district:
        print(f"  {p['district_en']}: {p['status']}")
    if final_feats:
        f0 = final_feats[0]
        print("Пример:", json.dumps(
            {"geometry_type": f0["geometry"]["type"],
             "properties": f0["properties"]},
            ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
