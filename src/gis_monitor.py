"""gis_monitor.py — Трек 1 (GIS и ДЗЗ) поверх существующего Qagro.

Простыми словами (для агронома):
  Берём поля из OSM (data/fields/akmola_osm_fields.geojson) и смотрим,
  как зеленела масса летом 2024 по спутниковым снимкам Sentinel-2.
  Зелень меряем индексом NDVI: чем ближе к 1, тем гуще растения.
  Если NDVI ровный и низкий — поле, возможно, не сеяли.
  Если NDVI низкий с провалами — всходы изреженные.
  Иначе — поле обрабатывается.

Как считается (честно, без выдумок):
  - Сцены НЕ ищем заново: scene_id переиспользуем из
    data/ndvi/ndvi_timeseries.json того же района (там поиск через
    Microsoft Planetary Computer STAC, collection sentinel-2-l2a).
  - Для каждой даты берём до 2 сцен с ТОЧНОЙ датой из этого файла.
    Нет сцены на дату -> ndvi_mean=None с причиной (число не выдумываем).
  - NDVI считаем на сервере PC TiTiler:
    POST https://planetarycomputer.microsoft.com/api/data/v1/item/statistics
    params: collection=sentinel-2-l2a, item=<scene_id>,
            assets=B04 & B08, expression=(B08-B04)/(B08+B04),
            asset_as_band=true
    body: GeoJSON Feature с прямоугольником bbox поля.
    Ответ: statistics mean — это и есть ndvi_mean.
    (GET с ?bbox= игнорируется сервером — проверено 19.09.2026:
    GET отдаёт среднее по всей сцене, поэтому используем POST.)
  - Bbox поля считаем из geometry и сжимаем до <=0.02 градуса
    (центр +/-0.01) — так быстрее (~1 c на запрос).
    Это приближение: берём прямоугольник, а не точную маску поля.
  - Лимиты: не более 6 полей за запуск, таймаут 25 с на запрос.
    Ошибка сети/сервера -> ndvi_mean=None с причиной.

Пороги классификации — ЭВРИСТИКИ из агро-практики, НЕ ГОСТ:
  amplitude = ndvi_max - ndvi_min по датам с данными.
  - amplitude < 0.15            -> likely_fallow ("возможно не обрабатывается")
  - иначе ndvi_max < 0.35       -> sparse ("изреженные / возможна гибель")
  - иначе                       -> cultivated ("обрабатывается")
  dead_share = доля дат с ndvi < 0.3 (0..1) среди дат с данными.

Источники хакатона (см. также data/gis/GIS_README.md):
  Sentinel-2: Copernicus Browser https://browser.dataspace.copernicus.eu/,
    Sentinel Hub https://www.sentinel-hub.com/,
    PC STAC https://planetarycomputer.microsoft.com/api/stac/v1
  Landsat 8/9 (ручная проверка): USGS EarthExplorer https://earthexplorer.usgs.gov/,
    LandsatLook https://landsatlook.usgs.gov/
  OSM/Geofabrik (ODbL): https://www.openstreetmap.org/copyright,
    https://download.geofabrik.de/asia/kazakhstan.html
  QGIS: GeoJSON открывается напрямую (см. GIS_README).
  EarthMap (ручная проверка): https://www.earthmap.org/

Запуск:
  python src/gis_monitor.py --district Esil --max 4
Выход:
  data/gis/gis_{district}.json  (по каждому полю: серия NDVI + класс)
  data/gis/gis_summary.json     (итоги: total_fields/checked/cultivated/...)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]
FIELDS_GEOJSON = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
NDVI_TS = ROOT / "data" / "ndvi" / "ndvi_timeseries.json"
GIS_DIR = ROOT / "data" / "gis"

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
TITILER_ITEM_STATS = "https://planetarycomputer.microsoft.com/api/data/v1/item/statistics"
COLLECTION = "sentinel-2-l2a"
EXPRESSION = "(B08-B04)/(B08+B04)"

DEFAULT_DATES = ["2024-06-03", "2024-06-13", "2024-06-18", "2024-07-23", "2024-07-31", "2024-08-12"]
MAX_EXTRA_DATES = 4  # доп. дат района сверх DEFAULT (равномерно по сезону)
MAX_FIELDS_HARD = 6
TIMEOUT_S = 25
MAX_DEG = 0.02  # сжатие bbox для скорости

# Пороги — эвристики агро-практики, НЕ ГОСТ (см. classify_field).
AMP_FALLOW = 0.15
MAX_SPARSE = 0.35
DEAD_NDVI = 0.3

STATUS_RU = {
    "cultivated": "Поле обрабатывается, зелёная масса есть",
    "sparse": "Изреженные посевы / возможна гибель (низкий максимум NDVI)",
    "likely_fallow": "Возможно, поле не обрабатывается (NDVI ровный и низкий)",
    "no_data": "Нет данных NDVI (все запросы неуспешны)",
}

STATUS_KZ = {
    "cultivated": "Егістік өңделеді, жасыл масса бар",
    "sparse": "Сирек егін / жойылуы мүмкін (NDVI төмен)",
    "likely_fallow": "Егістік өңделмеген болуы мүмкін (NDVI тегіс және төмен)",
    "no_data": "NDVI дерегі жоқ",
}

STATUS_EN = {
    "cultivated": "Field is cultivated, green biomass present",
    "sparse": "Sparse stand / possible loss (low NDVI peak)",
    "likely_fallow": "Possibly not cultivated (flat low NDVI)",
    "no_data": "No NDVI data",
}


# ------------------------------------------------------------ загрузка
def _load_fields() -> list[dict]:
    fc = json.loads(FIELDS_GEOJSON.read_text(encoding="utf-8"))
    return fc.get("features", []) or []


def _load_scenes_index() -> dict[tuple[str, str], list[str]]:
    """(district, date) -> до 2 scene_id из ndvi_timeseries.json (порядок файла)."""
    try:
        raw = json.loads(NDVI_TS.read_text(encoding="utf-8"))
    except Exception:
        return {}
    idx: dict[tuple[str, str], list[str]] = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        dis, dat, sid = r.get("district"), r.get("date"), r.get("scene_id")
        if not (dis and dat and sid):
            continue
        key = (str(dis), str(dat))
        lst = idx.setdefault(key, [])
        if sid not in lst and len(lst) < 2:
            lst.append(sid)
    return idx


# ------------------------------------------------------------ bbox
def field_bbox(field: dict) -> tuple[list[float], bool]:
    """Bbox [minlon,minlat,maxlon,maxlat] из geometry, сжатый до <=0.02deg.

    Возвращает (bbox, squeezed). Для скорости берём прямоугольник,
    а не попиксельную маску поля (ограничение описано в GIS_README).
    """
    geom = (field or {}).get("geometry") or {}
    gtype = geom.get("type")
    coords: list = []
    try:
        if gtype == "Polygon":
            coords = (geom.get("coordinates") or [[]])[0]
        elif gtype == "MultiPolygon":
            for poly in geom.get("coordinates") or []:
                for ring in poly or []:
                    coords.extend(ring)
    except Exception:
        coords = []
    if len(coords) < 3:
        # запасной вариант: центр района Esil (честно помечаем)
        return [66.39, 51.94, 66.41, 51.96], False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    minlon, maxlon = min(lons), max(lons)
    minlat, maxlat = min(lats), max(lats)
    clon, clat = (minlon + maxlon) / 2.0, (minlat + maxlat) / 2.0
    squeezed = False
    if maxlon - minlon > MAX_DEG:
        minlon, maxlon = clon - MAX_DEG / 2.0, clon + MAX_DEG / 2.0
        squeezed = True
    if maxlat - minlat > MAX_DEG:
        minlat, maxlat = clat - MAX_DEG / 2.0, clat + MAX_DEG / 2.0
        squeezed = True
    return [float(minlon), float(minlat), float(maxlon), float(maxlat)], squeezed


# ------------------------------------------------------------ TiTiler
def _import_requests():
    """Импорт requests (конфликта имён больше нет после переименования)."""
    import requests as _rq
    return _rq


def _titiler_ndvi(scene_id: str, bbox: list[float]) -> tuple[float | None, str]:
    """Один запрос к PC TiTiler. Возвращает (ndvi_mean|None, пояснение)."""
    requests = _import_requests()

    minlon, minlat, maxlon, maxlat = bbox
    ring = [[minlon, minlat], [maxlon, minlat], [maxlon, maxlat],
            [minlon, maxlat], [minlon, minlat]]
    feat = {"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}
    params = [("collection", COLLECTION), ("item", scene_id),
              ("assets", "B04"), ("assets", "B08"),
              ("expression", EXPRESSION), ("asset_as_band", "true")]
    try:
        r = requests.post(TITILER_ITEM_STATS, params=params, json=feat,
                          timeout=TIMEOUT_S)
        if r.status_code != 200:
            return None, f"TITILER HTTP {r.status_code}: {r.text[:200]}"
        payload = r.json()
        stats = (payload.get("properties") or {}).get("statistics") or {}
        if EXPRESSION not in stats and stats:
            # ключ может отличаться пробелами — берём первую запись
            key = next(iter(stats))
            stats = {EXPRESSION: stats[key]}
        entry = stats.get(EXPRESSION)
        if not isinstance(entry, dict):
            return None, "TITILER: нет блока statistics в ответе"
        mean = entry.get("mean")
        if not isinstance(mean, (int, float)):
            return None, "TITILER: mean не число"
        mean = float(mean)
        if not (-1.0 <= mean <= 1.0):
            return None, f"TITILER: mean вне [-1,1]: {mean}"
        n = entry.get("valid_pixels")
        return round(mean, 4), f"ok via PC TiTiler POST (valid_pixels={n})"
    except Exception as e:  # таймаут/сеть/JSON — честный None
        return None, f"{type(e).__name__}: {str(e)[:200]}"


# ------------------------------------------------------------ серия поля
def _district_dates(district_en: str) -> list[str]:
    """Даты проверки района: DEFAULT (2024) + даты его сцен из JSON.

    Без этого районы со сценами только 2025 (все, кроме Esil/Zerenda/Zhaksy)
    получали бы вечный no_data: scene reuse идёт по (район, дата).
    Доп. дат не более MAX_EXTRA_DATES, равномерно по сезону (скорость).
    """
    idx = _load_scenes_index()
    extra = sorted({d for (dis, d) in idx
                    if dis == district_en and d not in DEFAULT_DATES})
    if len(extra) > MAX_EXTRA_DATES:
        step = len(extra) / MAX_EXTRA_DATES
        extra = [extra[int(i * step)] for i in range(MAX_EXTRA_DATES)]
    return list(DEFAULT_DATES) + extra


def field_ndvi(field: dict, dates: list[str] | None = None) -> list[dict]:
    """NDVI-серия поля: [{date, ndvi_mean|None, scene_id|None, note}]."""
    if dates is None:
        props0 = (field or {}).get("properties") or {}
        dates = _district_dates(str(props0.get("district_en") or ""))
    props = (field or {}).get("properties") or {}
    district = str(props.get("district_en") or "")
    bbox, _ = field_bbox(field)
    idx = _load_scenes_index()
    series: list[dict] = []
    for date in dates:
        scenes = idx.get((district, date), [])[:2]  # 1-2 сцены, scene_id reuse
        if not scenes:
            series.append({"date": date, "ndvi_mean": None, "scene_id": None,
                           "note": "no scene: в ndvi_timeseries.json нет сцены "
                                   f"{district} на {date} — число не выдумываем"})
            continue
        ok_vals: list[float] = []
        used: list[str] = []
        last_err = ""
        for sid in scenes:
            mean, info = _titiler_ndvi(sid, bbox)
            if mean is None:
                last_err = info
                continue
            ok_vals.append(mean)
            used.append(sid)
        if ok_vals:
            avg = round(sum(ok_vals) / len(ok_vals), 4)
            series.append({"date": date, "ndvi_mean": avg,
                           "scene_id": "+".join(used),
                           "note": f"real via PC TiTiler ({len(used)} сцена(ы))"})
        else:
            series.append({"date": date, "ndvi_mean": None,
                           "scene_id": "+".join(scenes),
                           "note": f"TITILER fail: {last_err} — число не выдумываем"})
    return series


# ------------------------------------------------------------ классификация
def classify_field(series: list[dict]) -> dict:
    """Классификация серии NDVI.

    Пороги — ЭВРИСТИКИ из агро-практики, НЕ ГОСТ:
      amplitude < 0.15  -> likely_fallow
      ndvi_max < 0.35   -> sparse
      иначе             -> cultivated
    dead_share — доля дат с данными, где ndvi < 0.3.
    """
    vals = []
    for p in series or []:
        m = (p or {}).get("ndvi_mean")
        if isinstance(m, (int, float)) and -1.0 <= float(m) <= 1.0:
            vals.append(float(m))
    if not vals:
        return {"ndvi_max": None, "ndvi_min": None, "amplitude": None,
                "dead_share": None, "status": "no_data",
                "status_ru": STATUS_RU["no_data"],
                "status_kz": STATUS_KZ["no_data"],
                "status_en": STATUS_EN["no_data"],
                "thresholds_note": "пороги — эвристики агро-практики, не ГОСТ"}
    ndvi_max = round(max(vals), 4)
    ndvi_min = round(min(vals), 4)
    amplitude = round(ndvi_max - ndvi_min, 4)
    dead_share = round(sum(1 for v in vals if v < DEAD_NDVI) / len(vals), 4)
    if amplitude < AMP_FALLOW:  # эвристика: плоский ход = поле не сеяли/пар
        status = "likely_fallow"
    elif ndvi_max < MAX_SPARSE:  # эвристика: низкий пик = изреженность/гибель
        status = "sparse"
    else:
        status = "cultivated"
    return {"ndvi_max": ndvi_max, "ndvi_min": ndvi_min,
            "amplitude": amplitude, "dead_share": dead_share,
            "status": status, "status_ru": STATUS_RU[status],
            "status_kz": STATUS_KZ[status], "status_en": STATUS_EN[status],
            "thresholds_note": "пороги amplitude<0.15 / max<0.35 — эвристики агро-практики, не ГОСТ"}


# ------------------------------------------------------------ район
def _field_id(field: dict, i: int) -> str:
    props = (field or {}).get("properties") or {}
    for k in ("demo_id", "osm_id", "osm_name", "id"):
        v = props.get(k)
        if v is not None and str(v) != "None":
            return f"{props.get('district_en')}_{v}"
    return f"{props.get('district_en', 'field')}_{i}"


def run_district(district_en: str, max_fields: int = 6) -> dict:
    """Проверить до max_fields (жёсткий потолок 6) района.

    Пишет data/gis/gis_{district}.json и data/gis/gis_summary.json,
    возвращает summary-словарь.
    """
    max_fields = max(1, min(int(max_fields), MAX_FIELDS_HARD))
    all_fields = [f for f in _load_fields()
                  if (f.get("properties") or {}).get("district_en") == district_en]
    total_fields = len(all_fields)
    todo = all_fields[:max_fields]
    dates = _district_dates(district_en)
    out_fields: list[dict] = []
    counts = {"cultivated": 0, "sparse": 0, "likely_fallow": 0, "no_data": 0}
    max_vals: list[float] = []
    for i, field in enumerate(todo):
        props = field.get("properties") or {}
        bbox, squeezed = field_bbox(field)
        series = field_ndvi(field, dates)
        cls = classify_field(series)
        st = cls.get("status")
        if st in counts:
            counts[st] += 1
        if isinstance(cls.get("ndvi_max"), (int, float)):
            max_vals.append(float(cls["ndvi_max"]))
        out_fields.append({
            "field_id": _field_id(field, i),
            "area_ha": props.get("area_ha"),
            "demo": bool(props.get("demo")),
            "source": props.get("source"),
            "bbox_used": [round(v, 5) for v in bbox],
            "bbox_squeezed_to_0_02": squeezed,
            "series": series,
            "classification": cls,
        })
    GIS_DIR.mkdir(parents=True, exist_ok=True)
    detail = {
        "district": district_en,
        "dates": dates,
        "method": "OSM-поля (bbox<=0.02deg) + Sentinel-2 L2A NDVI=(B08-B04)/(B08+B04) "
                  "через PC STAC (scene reuse) + PC TiTiler POST /item/statistics; "
                  "пороги — эвристики агро-практики, не ГОСТ",
        "sources": {
            "fields": "OSM via Overpass (ODbL) + Geofabrik backup; demo:true — не OSM",
            "sentinel2_stac": STAC_URL,
            "sentinel2_titiler": TITILER_ITEM_STATS,
            "copernicus_browser": "https://browser.dataspace.copernicus.eu/",
            "sentinel_hub": "https://www.sentinel-hub.com/",
            "landsat_look": "https://landsatlook.usgs.gov/",
            "usgs_earthexplorer": "https://earthexplorer.usgs.gov/",
            "earthmap": "https://www.earthmap.org/",
        },
        "limits": "bbox-приближение вместо попиксельной маски поля; "
                  "облака отфильтрованы на уровне сцен (cloud<20% в STAC); "
                  "нет сцены на дату -> None без выдумок",
        "total_fields": total_fields,
        "checked": len(out_fields),
        "fields": out_fields,
    }
    (GIS_DIR / f"gis_{district_en}.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    avg_max = round(sum(max_vals) / len(max_vals), 4) if max_vals else None
    summary = {"district": district_en,
               "total_fields": total_fields, "checked": len(out_fields),
               "cultivated": counts["cultivated"], "sparse": counts["sparse"],
               "likely_fallow": counts["likely_fallow"],
               "no_data": counts["no_data"], "avg_ndvi_max": avg_max,
               "fields": out_fields}
    (GIS_DIR / "gis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GIS-мониторинг полей (Трек 1): NDVI Sentinel-2 по OSM-полям.")
    ap.add_argument("--district", default="Esil", help="district_en, напр. Esil")
    ap.add_argument("--max", dest="max_fields", type=int, default=6,
                    help="полей проверить (потолок 6)")
    args = ap.parse_args(argv)
    print(f"[gis] район {args.district}, макс. полей: {min(args.max_fields, MAX_FIELDS_HARD)}", flush=True)
    summary = run_district(args.district, args.max_fields)
    print(f"[gis] проверено: {summary['checked']} из {summary['total_fields']}", flush=True)
    print(f"[gis] cultivated={summary['cultivated']} sparse={summary['sparse']} "
          f"likely_fallow={summary['likely_fallow']} no_data={summary['no_data']} "
          f"avg_ndvi_max={summary['avg_ndvi_max']}", flush=True)
    print(f"[gis] файлы: data/gis/gis_{args.district}.json + data/gis/gis_summary.json", flush=True)
    detail = json.loads((GIS_DIR / f"gis_{args.district}.json").read_text(encoding="utf-8"))
    for f in detail.get("fields", []):
        cls = f.get("classification", {})
        seq = ", ".join(f"{p['date']}:{p['ndvi_mean']}" for p in f.get("series", []))
        print(f"  - {f['field_id']} ({f.get('area_ha')} га): "
              f"{cls.get('status')} ({cls.get('status_ru')}), "
              f"max={cls.get('ndvi_max')} amp={cls.get('amplitude')} "
              f"dead_share={cls.get('dead_share')} | {seq}", flush=True)
    print("DONE gis_monitor.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
