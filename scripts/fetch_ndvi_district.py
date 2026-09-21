"""fetch_ndvi_district.py — настоящие NDVI Sentinel-2 для района без покрытия.

Проблема: data/ndvi/ndvi_timeseries.json содержит сцены только Esil/Zerenda,
поэтому src/gis_monitor.py для остальных районов возвращает no_data
("все запросы неуспешны" — сцены неоткуда взять; сеть тут ни при чём).

Что делает (только реальные данные, без выдумок):
  1. Берёт самое большое OSM-поле района (настоящая пашня, не центроид),
     bbox сжимает до 0.02deg (как gis_monitor.field_bbox).
  2. Ищет сцены Sentinel-2 L2A cloud<20% за июнь–август 2024–2025 через
     PC STAC (reuse src.sentinel_ndvi._search).
  3. Для каждой даты (до 2 сцен с минимальной облачностью) считает настоящий
     NDVI через PC TiTiler POST /item/statistics (reuse src.gis_monitor).
  4. Дописывает {district, date, ndvi_mean, scene_id, status} в
     data/ndvi/ndvi_timeseries.json, НЕ трогая существующие записи
     (дедуп по (district, date, scene_id)). Неуспешные даты в файл не идут
     (причины — в stdout); число не выдумывается.

Запуск:
  python scripts/fetch_ndvi_district.py --district Zhaksy [--max-dates 12]
Выход — всегда exit 0 (как sentinel_ndvi.py), итог в stdout.
Повторный python src/sentinel_ndvi.py новые записи НЕ затрёт (keep-блок C8).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gis_monitor import _load_fields, _titiler_ndvi, field_bbox  # noqa: E402
from src.sentinel_ndvi import _search  # noqa: E402
from src.sentinel_ndvi import CLOUD_LT, SEASONS  # noqa: E402

OUT_JSON = ROOT / "data" / "ndvi" / "ndvi_timeseries.json"


def _rep_bbox(district_en: str, allow_demo: bool = False) -> tuple[list[float], str, bool]:
    """Bbox самого большого OSM-поля района + его id (честная пашня)."""
    fields = [f for f in _load_fields()
              if ((f.get("properties") or {}).get("district_en") == district_en
                  and (allow_demo or not (f.get("properties") or {}).get("demo")))]
    if not fields:
        raise ValueError(f"В {district_en} нет OSM-полей (только demo или пусто).")
    best = max(fields,
               key=lambda f: float((f.get("properties") or {}).get("area_ha") or 0))
    bbox, squeezed = field_bbox(best)
    props = best.get("properties") or {}
    fid = str(props.get("osm_id") or props.get("id") or "?")
    is_demo = bool(props.get("demo"))
    print(f"[ndvi-district] {district_en}: поле {district_en}_{fid} "
          f"({props.get('area_ha')} га, demo={is_demo}), bbox={bbox} squeezed={squeezed}",
          flush=True)
    return bbox, f"{district_en}_{fid}", is_demo


def _pick_dates(items: list[dict], max_dates: int) -> list[str]:
    """Даты с мин. облачностью; если дат больше лимита — равномерно по сезону."""
    by_date: dict[str, list[dict]] = {}
    for it in items:
        if it.get("date") and it.get("scene_id"):
            by_date.setdefault(it["date"], []).append(it)
    for lst in by_date.values():
        lst.sort(key=lambda x: (x.get("cloud") is None, x.get("cloud") or 99))
    dates = sorted(by_date)
    if len(dates) > max_dates:
        step = len(dates) / max_dates
        dates = [dates[int(i * step)] for i in range(max_dates)]
    return [(d, by_date[d][:2]) for d in dates]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Добрать настоящие NDVI района.")
    ap.add_argument("--district", required=True, help="district_en, напр. Zhaksy")
    ap.add_argument("--max-dates", type=int, default=12,
                    help="макс. дат NDVI (дефолт 12)")
    ap.add_argument("--allow-demo", action="store_true",
                    help="разрешить demo-поле (напр. Kokshetau: все 3 поля demo; "
                         "NDVI настоящий, граница примерная — помечается в status)")
    args = ap.parse_args(argv)

    bbox, fid, is_demo = _rep_bbox(args.district, allow_demo=args.allow_demo)
    found: list[dict] = []
    for year, dt in SEASONS:
        try:
            items, backend = _search(bbox, dt)
            print(f"[ndvi-district] STAC {year}: {len(items)} сцен ({backend})",
                  flush=True)
            found.extend(items)
        except Exception as e:
            print(f"[ndvi-district] STAC {year} FAIL: {type(e).__name__}: {e}",
                  flush=True)
    if not found:
        print("[ndvi-district] сцен нет — файл не меняем (числа не выдумываем).",
              flush=True)
        return 0

    try:
        existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    seen = {(r.get("district"), r.get("date"), r.get("scene_id")) for r in existing
            if isinstance(r, dict)}

    added = skipped = failed = 0
    for date, scenes in _pick_dates(found, args.max_dates):
        for sc in scenes:
            sid = sc.get("scene_id")
            if (args.district, date, sid) in seen:
                skipped += 1
                continue
            mean, info = _titiler_ndvi(sid, bbox)
            if mean is None:
                failed += 1
                print(f"  {date} {sid}: TITILER FAIL ({info})", flush=True)
                continue
            existing.append({
                "district": args.district,
                "date": date,
                "ndvi_mean": mean,
                "scene_id": sid,
                "status": f"real via PC TiTiler for rep-field {fid} "
                          f"(cloud={sc.get('cloud')}, scripts/fetch_ndvi_district.py)"
                          + (" [demo-bbox: граница примерная]" if is_demo else ""),
            })
            seen.add((args.district, date, sid))
            added += 1
            print(f"  {date} {sid}: NDVI={mean} (cloud={sc.get('cloud')})", flush=True)
    OUT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[ndvi-district] добавлено: {added}, пропущено (уже есть): {skipped}, "
          f"неуспешно: {failed} -> {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
