"""sentinel_ndvi.py — v2 NDVI Sentinel-2 demo (ЧЕСТНО, без выдуманных NDVI).

Что делает:
  - Для 2 демо-полей (Esil 51.95,66.40 и Zerenda 53.05,69.15, bbox 0.02deg)
    за июнь-август 2024-2025 ищет сцены Sentinel-2 L2A с cloud<20% через
    Microsoft Planetary Computer STAC (без ключа):
      https://planetarycomputer.microsoft.com/api/stac/v1
      collection sentinel-2-l2a
  - Пытается pystac-client + planetary-computer; если их нет — fallback
    на plain requests POST /search (requests уже в зависимостях).
  - Скачивание B04/B08 и расчёт NDVI НЕ выполняется автоматически
    (требует rasterio + тяжёлые COG; для пилота — ручной источник, см. README).
    Поэтому ndvi_mean ВСЕГДА None (MISSING) — число НЕ выдумываем.
  - Сохраняет data/ndvi/ndvi_timeseries.json — список записей:
      {district, date, ndvi_mean|None, scene_id, status}
    status: "listed" (сцена найдена, NDVI=MISSING) или "error: ..." (STAC
    недоступен / библиотек нет / сеть упала).
  - C8: ранее полученные НАСТОЯЩИЕ ndvi_mean других районов (напр. Zhaksy
    через scripts/fetch_ndvi_district.py) при перезапуске НЕ затираются —
    дописываются как есть (см. keep-блок в main()).
  - Модель ОБЯЗАНА работать без NDVI: src/features_ndvi.py делает optional
    join (если все ndvi_mean None или файла нет — фича пропускается),
    train.py / predict.py используют базовые фичи.

Запуск:
  python src/sentinel_ndvi.py
Выход — всегда exit 0 (даже при error-статусах), чтобы не ломать пайплайн.
Честный ручной источник для пилота — см. README-блок Sentinel-2:
  Copernicus Browser https://browser.dataspace.copernicus.eu/
  Sentinel Hub https://www.sentinel-hub.com/
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

if "PYTEST_CURRENT_TEST" not in os.environ:  # не трогаем capture pytest
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "ndvi"
OUT_JSON = OUT_DIR / "ndvi_timeseries.json"

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

DEMO_FIELDS = [
    {"district_en": "Esil", "lat": 51.95, "lon": 66.40},
    {"district_en": "Zerenda", "lat": 53.05, "lon": 69.15},
]
HALF_DEG = 0.01  # полный bbox 0.02deg
SEASONS = [
    (2024, "2024-06-01T00:00:00Z/2024-08-31T23:59:59Z"),
    (2025, "2025-06-01T00:00:00Z/2025-08-31T23:59:59Z"),
]
CLOUD_LT = 20
LIMIT = 50
TIMEOUT = 30


def _bbox(lon: float, lat: float) -> list[float]:
    return [lon - HALF_DEG, lat - HALF_DEG, lon + HALF_DEG, lat + HALF_DEG]


def _search_pystac(bbox: list[float], dt: str) -> list[dict]:
    """Поиск через pystac-client. Возвращает [{scene_id, date, cloud}]."""
    from pystac_client import Client  # type: ignore

    client = Client.open(STAC_URL, timeout=TIMEOUT)
    search = client.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=dt,
        query={"eo:cloud_cover": {"lt": CLOUD_LT}},
        limit=LIMIT,
    )
    out: list[dict] = []
    for item in search.items():
        dt_val = getattr(item, "datetime", None)
        d = dt_val.date().isoformat() if dt_val is not None else None
        cloud = None
        try:
            cloud = float(item.properties.get("eo:cloud_cover"))
        except Exception:
            cloud = None
        out.append({"scene_id": item.id, "date": d, "cloud": cloud})
    return out


def _search_requests(bbox: list[float], dt: str) -> list[dict]:
    """Fallback без pystac-client: plain requests POST /search."""
    import requests

    body = {
        "collections": [COLLECTION],
        "bbox": bbox,
        "datetime": dt,
        "query": {"eo:cloud_cover": {"lt": CLOUD_LT}},
        "limit": LIMIT,
    }
    r = requests.post(STAC_URL + "/search", json=body, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"STAC HTTP {r.status_code}: {r.text[:500]}")
    payload = r.json()
    feats = payload.get("features", [])
    out: list[dict] = []
    for f in feats:
        props = f.get("properties", {}) or {}
        out.append({
            "scene_id": f.get("id"),
            "date": (props.get("datetime") or "")[:10] or None,
            "cloud": props.get("eo:cloud_cover"),
        })
    return out


def _search(bbox: list[float], dt: str) -> tuple[list[dict], str]:
    """Пробует pystac-client, затем requests. Возвращает (сцены, backend)."""
    try:
        items = _search_pystac(bbox, dt)
        return items, "pystac-client"
    except ImportError as e:
        print(f"  [info] pystac-client нет ({e}), fallback на requests...", flush=True)
    except Exception as e:
        print(f"  [warn] pystac-client поиск упал ({e}), пробую requests...", flush=True)
    items = _search_requests(bbox, dt)
    return items, "requests"


def _load_real_ndvi() -> dict[tuple[str, str], dict]:
    """Ранее полученные НАСТОЯЩИЕ ndvi_mean {(district, scene_id): запись}.

    C7: реальные NDVI берутся через PC TiTiler statistics (см. ndvi_timeseries.json).
    Повторный запуск поиска сцен не должен затирать их в None — сохраняем.
    Возвращает только записи с конечным числом ndvi_mean (не None).
    Ключ — (district, scene_id), а НЕ голый scene_id: один тайл Sentinel-2
    покрывает несколько районов, а ndvi_mean посчитан по bbox КОНКРЕТНОГО
    района — перенос значения в другой район был бы выдумкой (см. C9).
    """
    try:
        raw = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, dict):
        raw = raw.get("items", raw)
    out: dict[tuple[str, str], dict] = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        sid = r.get("scene_id")
        dis = r.get("district")
        m = r.get("ndvi_mean")
        if sid and dis and isinstance(m, (int, float)) and -1.0 <= m <= 1.0:
            out[(str(dis), str(sid))] = r
    return out


def _base_status(rec: dict) -> str:
    """Статус без нарастающих ' | kept...' суффиксов от прошлых реранов."""
    import re as _re

    return _re.sub(r"( \| kept.*)*$", "", str(rec.get("status", "")))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keep = _load_real_ndvi()
    if keep:
        print(f"[sentinel_ndvi] сохраняю {len(keep)} реальных ndvi_mean из {OUT_JSON}", flush=True)
    records: list[dict] = []
    n_listed = 0
    n_error = 0
    for field in DEMO_FIELDS:
        den = field["district_en"]
        bbox = _bbox(field["lon"], field["lat"])
        for year, dt in SEASONS:
            label = f"{den} {year} bbox={bbox}"
            print(f"[sentinel_ndvi] поиск {label} cloud<{CLOUD_LT}% ...", flush=True)
            try:
                items, backend = _search(bbox, dt)
                print(f"  -> {len(items)} сцен ({backend})", flush=True)
                if not items:
                    records.append({
                        "district": den,
                        "date": f"{year}-06-01",
                        "ndvi_mean": None,
                        "scene_id": None,
                        "status": f"listed_empty via {backend}: сцен cloud<{CLOUD_LT}% "
                                  f"не найдено; ndvi_mean=MISSING (число не выдумываем)",
                    })
                for it in items:
                    n_listed += 1
                    sid = it.get("scene_id")
                    if (den, sid) in keep:
                        # Не затираем настоящее значение, полученное через TiTiler (C7).
                        # Ключ (district, scene_id): C9 — значение чужого bbox
                        # сюда попасть не может.
                        k = keep[(den, sid)]
                        records.append({
                            "district": den,
                            "date": it.get("date"),
                            "ndvi_mean": k["ndvi_mean"],
                            "scene_id": sid,
                            "status": _base_status(k) + " | kept on rerun",
                        })
                        continue
                    records.append({
                        "district": den,
                        "date": it.get("date"),
                        "ndvi_mean": None,  # MISSING — не выдумываем число!
                        "scene_id": it.get("scene_id"),
                        "status": f"listed via {backend} (cloud={it.get('cloud')}): "
                                  f"ndvi_mean=MISSING — требуется ручное скачивание "
                                  f"B04/B08 (Copernicus Browser / Sentinel Hub, см. README)",
                    })
            except Exception as e:  # STAC недоступен — честный error, модель работает без NDVI
                n_error += 1
                msg = f"error: {type(e).__name__}: {e}"
                print(f"  -> {msg}", flush=True)
                records.append({
                    "district": den,
                    "date": f"{year}-06-01",
                    "ndvi_mean": None,
                    "scene_id": None,
                    "status": msg + " | модель работает без NDVI (optional join)",
                })
    # страховка: новые записи — только None; не-None допустим лишь
    # из ранее сохранённых настоящих значений (keep), числа не выдумываем
    for r in records:
        m = r.get("ndvi_mean")
        if m is not None and (r.get("district"), r.get("scene_id")) not in keep:
            raise RuntimeError("ndvi_mean должен быть None (MISSING) в v2 — числа не выдумываем")
    # C8: не теряем настоящие значения других районов (напр. Zhaksy из
    # scripts/fetch_ndvi_district.py): поиск ниже идёт только по DEMO_FIELDS,
    # поэтому дописываем keep-записи, которых нет в свежих результатах.
    seen = {(r.get("district"), r.get("date"), r.get("scene_id")) for r in records}
    for (dis, sid), rec in keep.items():
        key = (rec.get("district"), rec.get("date"), sid)
        if key not in seen:
            records.append({**rec, "status": _base_status(rec)
                            + " | kept (district not in DEMO_FIELDS)"})
            seen.add(key)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"[sentinel_ndvi] сцен найдено: {n_listed}, ошибок: {n_error}, "
          f"записей: {len(records)} -> {OUT_JSON}", flush=True)
    print("DONE sentinel_ndvi.py (модель работает без NDVI)", flush=True)


if __name__ == "__main__":
    main()
