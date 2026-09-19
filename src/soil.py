"""soil.py — SoilGrids v2.0 почвенные признаки по 10 районам (Qagro v4).

Канонический запрос из ТЗ (пробуем первым, как есть):
  https://rest.isric.org/soilgrids/v2.0/properties/query
    ?lon={lon}&lat={lat}&property=nitrogen,phh2o,soc,clay
    &depth=0-5cm,5-15cm&value=mean

ЗАДОКУМЕНТИРОВАННОЕ ОТКЛОНЕНИЕ (проверено 2026-09-19, серверная сторона):
  comma-форма multi-property сейчас отвечает HTTP 200 + телом
  "Internal Server Error", а comma-форма multi-depth — пустыми layers.
  Рабочая эквивалентная форма того же эндпоинта — повторные параметры:
    ?property=nitrogen&property=phh2o&property=soc&property=clay
    &depth=0-5cm&depth=5-15cm&value=mean
  Поодиночные запросы тоже работают. Поэтому логика честного фолбэка:
    1) пробуем канонический comma-URL (фиксируем статус в лог);
    2) если он упал/пуст — тянем те же свойства поодиночке
       (тот же эндпоинт, те же глубины/mean) и склеиваем слои.
  Значения идентичны тем, что отдал бы канонический запрос, —
  это не моки, а тот же SoilGrids API.

Выходы:
  data/raw/soil_{district_en}.json — сырой ответ (склейка слоёв + meta запроса)
  data/processed/soil.csv          — {district_en, nitrogen, ph, soc, clay}

Агрегация глубин: среднее доступных глубин 0-5cm и 5-15cm после
перевода в целевые единицы через d_factor из ответа:
  nitrogen: cg/kg /100 -> г/кг;  phh2o: pH*10 /10 -> pH;
  soc: dg/kg /10 -> г/кг;         clay: g/kg /10 -> г/кг.
Clay 243 (сырое) -> 24.3 г/кг = 2.43% — порядок величин для суглинков
Акмолинской области правдоподобен (проверка порядка, не валидация).

Правила: timeout 20с, при ошибке района — пропуск с логом, без моков.
Если ни один район не получен — soil.csv НЕ пишем, exit 1 с понятным
текстом (шаг 2 v4 тогда пропускается, см. metrics/MODEL_V4.md).
"""
from __future__ import annotations

import json
import os as _os
import sys as _sys

# BOOTSTRAP (первым, до import pandas): проектный src/calendar.py затеняет
# stdlib `calendar` при `python src/*.py` и роняет импорт pandas через _strptime.
try:
    import calendar as _cal_probe  # noqa: F401
    if not hasattr(_cal_probe, "day_abbr"):
        raise ImportError("stdlib calendar shadowed by src/calendar.py")
    del _cal_probe
except Exception:
    import importlib.util as _ilu
    _stdlib_cal = _os.path.join(_os.path.dirname(_os.__file__), "calendar.py")
    _spec = _ilu.spec_from_file_location("calendar", _stdlib_cal)
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules["calendar"] = _mod
    _spec.loader.exec_module(_mod)
    del _ilu, _spec, _mod, _stdlib_cal

import logging
import sys
from pathlib import Path

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("soil")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
SOIL_CSV = PROC / "soil.csv"

BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["nitrogen", "phh2o", "soc", "clay"]
DEPTHS = ["0-5cm", "5-15cm"]
TIMEOUT = 20  # секунд, по ТЗ
RETRIES = 3  # повторы при 429/timeout (лимит API ~5 запр/мин)
RETRY_WAIT = 65  # секунд ожидания после 429 (окно лимита — 1 минута)
PAUSE_BETWEEN_DISTRICTS = 15  # секунд между районами (не упираться в лимит)

# Сырое свойство -> (колонка soil.csv, делитель d_factor по документации ответа)
# d_factor берём из ответа по факту, здесь — ожидаемые значения для QC.
PROPERTY_SPECS = {
    "nitrogen": ("nitrogen", 100),  # cg/kg -> г/кг
    "phh2o": ("ph", 10),            # pH*10 -> pH
    "soc": ("soc", 10),             # dg/kg -> г/кг
    "clay": ("clay", 10),           # g/kg (сырое в десятках) -> г/кг
}


def load_districts() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ds = cfg.get("districts", [])
    if len(ds) != 10:
        raise ValueError(f"districts.yaml: ожидалось 10 районов, найдено {len(ds)}")
    return ds


def canonical_url(lat: float, lon: float) -> str:
    """Канонический comma-URL из ТЗ (для лога и первой попытки)."""
    props = ",".join(PROPERTIES)
    depths = ",".join(DEPTHS)
    return (f"{BASE_URL}?lon={lon}&lat={lat}"
            f"&property={props}&depth={depths}&value=mean")


def robust_url(lat: float, lon: float) -> str:
    """Эквивалент с повторными параметрами (обход серверного бага comma-формы)."""
    q = f"lon={lon}&lat={lat}"
    for p in PROPERTIES:
        q += f"&property={p}"
    for d in DEPTHS:
        q += f"&depth={d}"
    return f"{BASE_URL}?{q}&value=mean"


def single_url(lat: float, lon: float, prop: str) -> str:
    q = f"lon={lon}&lat={lat}&property={prop}"
    for d in DEPTHS:
        q += f"&depth={d}"
    return f"{BASE_URL}?{q}&value=mean"


def _get_json(url: str, label: str) -> dict:
    import time as _time
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = RuntimeError(f"SoilGrids недоступен ({label}): {e}")
            log.warning(f"[{label}] попытка {attempt}/{RETRIES}: {last} — повтор")
            _time.sleep(RETRY_WAIT if attempt < RETRIES else 0)
            continue
        if r.status_code == 429:
            last = RuntimeError(
                f"SoilGrids HTTP 429 ({label}): {r.text[:200]} — лимит ~5 запр/мин")
            log.warning(f"[{label}] попытка {attempt}/{RETRIES}: {last} — ждём {RETRY_WAIT}с")
            _time.sleep(RETRY_WAIT if attempt < RETRIES else 0)
            continue
        if r.status_code != 200:
            raise RuntimeError(
                f"SoilGrids HTTP {r.status_code} ({label}): {r.text[:300]}")
        body = r.text.strip()
        if body == "Internal Server Error" or not body.startswith("{"):
            raise RuntimeError(
                f"SoilGrids вернул ошибку сервера ({label}): {body[:300]}")
        try:
            return r.json()
        except ValueError as e:
            raise RuntimeError(f"SoilGrids вернул не-JSON ({label})") from e
    raise last  # type: ignore[misc]  # все попытки — 429/timeout


def _layers_of(payload: dict) -> list[dict]:
    try:
        return payload.get("properties", {}).get("layers", []) or []
    except AttributeError:
        return []


def fetch_district(district_en: str, lat: float, lon: float) -> dict:
    """Тянет слои SoilGrids для района. Возвращает payload для кэша.

    Пробует канонический URL, при неудаче — поодиночные запросы.
    Бросает RuntimeError, если ничего не вышло (вызывающий пропускает с логом).
    """
    canon = canonical_url(lat, lon)
    log.info(f"[{district_en}] GET canonical: {canon}")
    try:
        payload = _get_json(canon, f"{district_en}/canonical")
        layers = _layers_of(payload)
        have = {ly.get("name") for ly in layers}
        if len(layers) >= len(PROPERTIES) and set(PROPERTIES) <= have:
            log.info(f"[{district_en}] canonical OK: слоёв {len(layers)}")
            payload["_qagro"] = {"mode": "canonical", "url": canon}
            return payload
        log.warning(f"[{district_en}] canonical пуст/неполон "
                    f"(слоёв {len(layers)}: {sorted(have)}) — фолбэк на поодиночные")
    except RuntimeError as e:
        log.warning(f"[{district_en}] canonical не сработал: {e} — фолбэк на поодиночные")

    # Фолбэк: тот же эндпоинт, по одному свойству (повторные depth-параметры)
    merged_layers: list[dict] = []
    errors: list[str] = []
    for prop in PROPERTIES:
        url = single_url(lat, lon, prop)
        try:
            p = _get_json(url, f"{district_en}/{prop}")
            ls = _layers_of(p)
            if not ls:
                errors.append(f"{prop}: пустые layers")
                continue
            merged_layers.extend(ls)
            log.info(f"[{district_en}] {prop}: OK "
                     f"(глубин: {len(ls[0].get('depths', []))})")
        except RuntimeError as e:
            errors.append(f"{prop}: {e}")
            log.warning(f"[{district_en}] {prop} не сработал: {e}")
    if len({ly.get("name") for ly in merged_layers}) < len(PROPERTIES):
        raise RuntimeError(f"[{district_en}] неполный набор слоёв "
                           f"({len(merged_layers)}): " + "; ".join(errors))
    log.info(f"[{district_en}] фолбэк OK: слоёв {len(merged_layers)}")
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"layers": merged_layers},
            "_qagro": {"mode": "per-property-fallback",
                       "canonical_url": canon,
                       "errors": errors}}


def parse_means(payload: dict) -> dict[str, float]:
    """Слои -> {nitrogen, ph, soc, clay} (среднее глубин в целевых единицах)."""
    out: dict[str, float] = {}
    layers = _layers_of(payload)
    by_name = {ly.get("name"): ly for ly in layers}
    for prop, (col, expected_factor) in PROPERTY_SPECS.items():
        ly = by_name.get(prop)
        if ly is None:
            raise ValueError(f"Нет слоя {prop} в ответе SoilGrids")
        factor = ly.get("unit_measure", {}).get("d_factor", expected_factor)
        try:
            factor = float(factor)
        except (TypeError, ValueError):
            factor = float(expected_factor)
        vals = []
        for d in ly.get("depths", []):
            v = (d.get("values") or {}).get("mean")
            if v is None:
                continue
            try:
                vals.append(float(v) / factor)
            except (TypeError, ValueError):
                continue
        if not vals:
            raise ValueError(f"Слой {prop}: нет mean-значений ни на одной глубине")
        out[col] = round(float(sum(vals) / len(vals)), 3)
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    import time as _time
    districts = load_districts()
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    failed: list[str] = []
    for i, d in enumerate(districts):
        en = d["name_en"]
        lat, lon = float(d["lat"]), float(d["lon"])
        cache = RAW / f"soil_{en}.json"
        # кэш-хит: готовый полный ответ переиспользуем без сети
        if cache.exists():
            try:
                means = parse_means(json.loads(cache.read_text(encoding="utf-8")))
                rows.append({"district_en": en, **means})
                log.info(f"[{en}] cache-hit: " + ", ".join(f"{k}={v}" for k, v in means.items()))
                continue
            except (ValueError, json.JSONDecodeError) as e:
                log.info(f"[{en}] кэш неполон ({e}) — докачиваем с API")
        if i > 0:
            _time.sleep(PAUSE_BETWEEN_DISTRICTS)
        try:
            payload = fetch_district(en, lat, lon)
            cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
            log.info(f"[{en}] кэш: {cache}")
            means = parse_means(payload)
            rows.append({"district_en": en, **means})
            log.info(f"[{en}] soil: " + ", ".join(f"{k}={v}" for k, v in means.items()))
        except (RuntimeError, ValueError) as e:
            failed.append(en)
            log.error(f"[{en}] ПРОПУСК (без моков): {e}")
    if failed:
        log.warning(f"Пропущено районов: {failed}")
    if not rows:
        log.error("SoilGrids: ни один район не получен — soil.csv НЕ писан. "
                  "Шаг 2 v4 для soil пропускается (см. metrics/MODEL_V4.md).")
        raise SystemExit(1)
    import pandas as pd
    df = pd.DataFrame(rows, columns=["district_en", "nitrogen", "ph", "soc", "clay"])
    df = df.sort_values("district_en").reset_index(drop=True)
    if df.isna().any().any():
        raise ValueError(f"NaN в soil-признаках:\n{df[df.isna().any(axis=1)]}")
    df.to_csv(SOIL_CSV, index=False)
    log.info(f"WROTE {SOIL_CSV} rows={len(df)} (успешно {len(rows)}/10)")


if __name__ == "__main__":
    main()
