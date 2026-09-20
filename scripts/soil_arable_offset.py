"""soil_arable_offset.py — проверка гипотезы: центроиды 5 null-районов попали
в города/леса (маска SoilGrids), а пашня рядом.

Для Atbasar, Esil, Shortandy, Bulandy, Kokshetau берёт центроид ПЕРВОГО
полигона района из data/fields/akmola_osm_fields.geojson (предпочтение —
реальный OSM demo=false; если OSM-полигонов нет — первый demo-fallback,
честно помечается) и запрашивает SoilGrids REST поодиночке, как soil.py
(single_url на каждое свойство, повторные depth-параметры, timeout 20с).

Успех  -> дописать data/processed/soil.csv (те же 4 свойства, source=arable-offset),
         сырой ответ — data/raw/soil_{en}_arable-offset.json (исходный
         soil_{en}.json с null НЕ перезаписывается — доказательство).
Провал  -> append-блок в metrics/MODEL_V4.md (дата, точки, результат).

Перезапускаемо: районы, уже закрытые в soil.csv не-null строкой, пропускаются;
блок в MODEL_V4.md дописывается один раз (guard по маркеру).
Без моков: при ошибке/пустых layers район фиксируется как null, exit 0
(частичный успех допустим), soil.csv пишется если есть >=1 строка.
Панель/модели не трогаются.
"""
from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("soil-offset")

ROOT = Path(__file__).resolve().parents[1]
GEOJSON = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
SOIL_CSV = PROC / "soil.csv"
REPORT = ROOT / "metrics" / "MODEL_V4.md"

BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["nitrogen", "phh2o", "soc", "clay"]
DEPTHS = ["0-5cm", "5-15cm"]
TIMEOUT = 20
RETRIES = 3
RETRY_WAIT = 65
PAUSE_BETWEEN_DISTRICTS = 15

TARGETS = ["Atbasar", "Esil", "Shortandy", "Bulandy", "Kokshetau"]

PROPERTY_SPECS = {
    "nitrogen": ("nitrogen", 100),
    "phh2o": ("ph", 10),
    "soc": ("soc", 10),
    "clay": ("clay", 10),
}


def poly_centroid(ring: list) -> tuple[float, float]:
    A = Cx = Cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = float(ring[i][0]), float(ring[i][1])
        x1, y1 = float(ring[i + 1][0]), float(ring[i + 1][1])
        c = x0 * y1 - x1 * y0
        A += c
        Cx += (x0 + x1) * c
        Cy += (y0 + y1) * c
    A /= 2.0
    if abs(A) < 1e-12:
        xs = [float(p[0]) for p in ring]
        ys = [float(p[1]) for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return Cx / (6 * A), Cy / (6 * A)


def first_field_point(district_en: str) -> dict:
    d = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feats = [f for f in d.get("features", [])
             if (f.get("properties") or {}).get("district_en") == district_en]
    if not feats:
        raise ValueError(f"{district_en}: нет полигонов в geojson")
    osm = [f for f in feats if not (f.get("properties") or {}).get("demo")]
    chosen = osm[0] if osm else feats[0]
    g = chosen.get("geometry") or {}
    if g.get("type") == "Polygon":
        ring = g["coordinates"][0]
    elif g.get("type") == "MultiPolygon":
        ring = g["coordinates"][0][0]
    else:
        raise ValueError(f"{district_en}: геометрия {g.get('type')} — не полигон")
    lon, lat = poly_centroid(ring)
    pr = chosen.get("properties") or {}
    return {"district_en": district_en, "lon": round(lon, 6), "lat": round(lat, 6),
            "osm_id": pr.get("osm_id"), "demo": bool(pr.get("demo")),
            "source": pr.get("source"), "area_ha": pr.get("area_ha"),
            "is_osm": bool(osm)}


def single_url(lat: float, lon: float, prop: str) -> str:
    q = f"lon={lon}&lat={lat}&property={prop}"
    for depth in DEPTHS:
        q += f"&depth={depth}"
    return f"{BASE_URL}?{q}&value=mean"


def _get_json(url: str, label: str) -> dict:
    import time as _time
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = RuntimeError(f"SoilGrids недоступен ({label}): {e}")
            log.warning(f"[{label}] попытка {attempt}/{RETRIES}: {last}")
            if attempt < RETRIES:
                _time.sleep(RETRY_WAIT)
            continue
        if r.status_code == 429:
            last = RuntimeError(f"SoilGrids HTTP 429 ({label}) — лимит ~5 запр/мин")
            log.warning(f"[{label}] попытка {attempt}/{RETRIES}: {last} — ждём {RETRY_WAIT}с")
            if attempt < RETRIES:
                _time.sleep(RETRY_WAIT)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"SoilGrids HTTP {r.status_code} ({label}): {r.text[:300]}")
        body = r.text.strip()
        if body == "Internal Server Error" or not body.startswith("{"):
            raise RuntimeError(f"SoilGrids ошибка сервера ({label}): {body[:300]}")
        try:
            return r.json()
        except ValueError as e:
            raise RuntimeError(f"SoilGrids не-JSON ({label})") from e
    raise last  # type: ignore[misc]


def fetch_point(district_en: str, lat: float, lon: float) -> dict:
    merged: list[dict] = []
    errors: list[str] = []
    for prop in PROPERTIES:
        url = single_url(lat, lon, prop)
        log.info(f"[{district_en}] GET {prop}: {url}")
        try:
            p = _get_json(url, f"{district_en}/{prop}")
            ls = (p.get("properties") or {}).get("layers") or []
            if not ls:
                errors.append(f"{prop}: пустые layers")
                continue
            merged.extend(ls)
            log.info(f"[{district_en}] {prop}: OK")
        except RuntimeError as e:
            errors.append(f"{prop}: {e}")
            log.warning(f"[{district_en}] {prop} FAIL: {e}")
    if len({ly.get("name") for ly in merged}) < len(PROPERTIES):
        raise RuntimeError(f"[{district_en}] неполный набор слоёв: " + "; ".join(errors))
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"layers": merged},
            "_qagro": {"mode": "arable-offset-per-property",
                       "point": {"lat": lat, "lon": lon}, "errors": errors}}


def parse_means(payload: dict) -> dict[str, float]:
    layers = (payload.get("properties") or {}).get("layers") or []
    by_name = {ly.get("name"): ly for ly in layers}
    out: dict[str, float] = {}
    for prop, (col, expected) in PROPERTY_SPECS.items():
        ly = by_name.get(prop)
        if ly is None:
            raise ValueError(f"Нет слоя {prop}")
        try:
            factor = float((ly.get("unit_measure") or {}).get("d_factor", expected))
        except (TypeError, ValueError):
            factor = float(expected)
        vals = []
        for dd in ly.get("depths", []):
            v = (dd.get("values") or {}).get("mean")
            if v is None:
                continue
            try:
                vals.append(float(v) / factor)
            except (TypeError, ValueError):
                continue
        if not vals:
            raise ValueError(f"Слой {prop}: mean=null на всех глубинах (genuine null)")
        out[col] = round(float(sum(vals) / len(vals)), 3)
    return out


def read_soil_csv() -> list[dict]:
    if not SOIL_CSV.exists():
        return []
    with open(SOIL_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    import time as _time
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    points = {t: first_field_point(t) for t in TARGETS}
    for t, p in points.items():
        tag = "OSM" if p["is_osm"] else "DEMO-fallback (OSM нет!)"
        log.info(f"[{t}] точка: lon={p['lon']} lat={p['lat']} [{tag}] "
                 f"osm_id={p['osm_id']} area_ha={p['area_ha']}")

    existing = read_soil_csv()
    have = {r["district_en"] for r in existing
            if all(r.get(k) not in (None, "") for k in ("nitrogen", "ph", "soc", "clay"))}
    todo = [t for t in TARGETS if t not in have]
    log.info(f"soil.csv уже закрыто: {sorted(have & set(TARGETS))}; к запросу: {todo}")

    ok: dict[str, dict] = {}
    fail: dict[str, str] = {}
    for i, t in enumerate(todo):
        p = points[t]
        if i > 0:
            _time.sleep(PAUSE_BETWEEN_DISTRICTS)
        try:
            payload = fetch_point(t, p["lat"], p["lon"])
            means = parse_means(payload)
            cache = RAW / f"soil_{t}_arable-offset.json"
            payload["_qagro"]["field_point"] = p
            cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
            ok[t] = means
            log.info(f"[{t}] SOIL-OFFSET: " + ", ".join(f"{k}={v}" for k, v in means.items()))
        except (RuntimeError, ValueError) as e:
            fail[t] = str(e)
            log.error(f"[{t}] СНОВА NULL/FAIL (без моков): {e}")

    if ok:
        rows = read_soil_csv()
        for r in rows:
            r.setdefault("source", "centroid")
            if not r.get("source"):
                r["source"] = "centroid"
        for t, means in ok.items():
            rows = [r for r in rows if r.get("district_en") != t]
            rows.append({"district_en": t, **{k: str(v) for k, v in means.items()},
                         "source": "arable-offset"})
        rows.sort(key=lambda r: r["district_en"])
        with open(SOIL_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["district_en", "nitrogen", "ph", "soc", "clay", "source"])
            w.writeheader()
            w.writerows(rows)
        log.info(f"WROTE {SOIL_CSV} rows={len(rows)} (offset закрыто: {sorted(ok)})")

    marker = f"arable-offset {date.today().isoformat()}"
    lines = [f"\n## 5. SoilGrids arable-offset — {date.today().isoformat()} "
             f"(гипотеза: центроиды в городах/лесу, пашня рядом)",
             "",
             "Точки — центроид первого полигона района из "
             "`data/fields/akmola_osm_fields.geojson`, запросы поодиночке как в "
             f"`src/soil.py` (timeout {TIMEOUT}с, без моков). Маркер: `{marker}`.",
             "",
             "| district_en | lon | lat | поле | osm_id | итог |",
             "|---|---|---|---|---|---|"]
    for t in TARGETS:
        p = points[t]
        field = "OSM" if p["is_osm"] else "demo-fallback (OSM нет)"
        if t in ok:
            m = ok[t]
            res = f"nitrogen={m['nitrogen']} ph={m['ph']} soc={m['soc']} clay={m['clay']}"
        elif t in fail:
            res = f"снова null/fail: {fail[t][:200]}"
        else:
            res = "уже был в soil.csv — пропущен (перезапуск)"
        lines.append(f"| {t} | {p['lon']} | {p['lat']} | {field} | {p['osm_id']} | {res} |")
    lines += ["",
              f"Закрыто offset-запросом в этом прогоне: {len(ok)}/5 " if todo
              else "Перезапуск: все 5 уже в soil.csv, новых запросов не было.",
              f"soil.csv: {len(read_soil_csv())} строк (колонка source: centroid/arable-offset).",
              "Панель/модели не тронуты.",
              ""]
    block = "\n".join(lines)
    cur = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if marker not in cur:
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(block)
        log.info(f"APPENDED {REPORT} [{marker}]")
    else:
        log.info(f"{REPORT}: блок [{marker}] уже есть — пропуск (перезапуск)")
    log.info(f"ИТОГ: закрыто {len(ok)}/{len(todo)} запрошенных; "
             f"провалы: {sorted(fail)}; всего offset в soil.csv: "
             f"{sorted(set(have) | set(ok))}")


if __name__ == "__main__":
    main()
