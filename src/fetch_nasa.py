"""fetch_nasa.py — NASA POWER monthly point -> сезонные агрегаты MJJA.

API: https://power.larc.nasa.gov/api/temporal/monthly/point
  ?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN,WS2M,GWETTOP
  &community=AG&longitude={lon}&latitude={lat}&start=2005&end=2025&format=JSON

Сезон: май-август (месяцы 5,6,7,8) каждого года, 2005-2025.
Агрегаты на район-год:
  tmean_mjja      — среднее T2M за MJJA
  tmax_mjja       — среднее T2M_MAX за MJJA
  tmin_mjja       — среднее T2M_MIN за MJJA
  precip_mjja_sum — сумма PRECTOTCORR (mm/month уже в месячной выдаче? в POWER
                    monthly PRECTOTCORR идёт в mm/day -> умножаем на дни месяца)
  heat_days_gt30  — ОЦЕНКА (!): из monthly нет дневных данных; эвристика
                    sum(max(0, T2M_MAX_m - 30) * 3.0) дней, округл. Документ.
                    Точный heat30 берётся из Open-Meteo daily в features.py.
  gdd_base5       — sum(max(0, T2M_m - 5) * days_in_month)
  vpd_proxy       — среднее VPD по MJJA (кПа) через Magnus из T2M и RH2M:
                    es = 0.6108*exp(17.27*T/(T+237.3)); ea = es*RH/100; vpd=es-ea
  Дополнительно: rh_mjja, sw_mjja (радиация), ws_mjja (ветер), gwet_mjja.

Выходы:
  data/raw/nasa_<district_en>.json   — сырой ответ POWER (как есть)
  data/raw/nasa_summary.csv          — район-год агрегаты

Громкий fail: HTTP != 200 / missing parameter / fill_value везде -999 /
пустой сезон -> исключение + exit 1. Никаких моков и заглушек.
"""
from __future__ import annotations

import calendar
import json
import logging
import math
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fetch_nasa")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"
RAW = ROOT / "data" / "raw"
SUMMARY = RAW / "nasa_summary.csv"

PARAMS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN,WS2M,GWETTOP"
SEASON = (5, 6, 7, 8)
START, END = 2005, 2025
TIMEOUT = 60
RETRIES = 4


def load_districts() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ds = cfg.get("districts", [])
    if not ds:
        raise ValueError("districts.yaml: empty districts")
    return ds


def power_url(lat: float, lon: float) -> str:
    return (
        "https://power.larc.nasa.gov/api/temporal/monthly/point"
        f"?parameters={PARAMS}&community=AG"
        f"&longitude={lon}&latitude={lat}&start={START}&end={END}&format=JSON"
    )


def fetch_one(lat: float, lon: float, label: str) -> dict:
    url = power_url(lat, lon)
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(f"NASA POWER HTTP {r.status_code}: {r.text[:500]}")
            payload = r.json()
            params = payload.get("properties", {}).get("parameter", {})
            if not params or "T2M" not in params:
                raise RuntimeError(f"NASA POWER missing T2M for {label}: keys={list(params)}")
            return payload
        except Exception as e:  # noqa: BLE001 — ретраим всё сетевое
            last = e
            log.warning("[%s] attempt %d/%d failed: %s", label, attempt, RETRIES, e)
            time.sleep(2 * attempt)
    raise RuntimeError(f"NASA POWER failed for {label} after {RETRIES} tries: {last}")


def vpd_kpa(tmean_c: float, rh_pct: float) -> float:
    es = 0.6108 * math.exp(17.27 * tmean_c / (tmean_c + 237.3))
    return max(0.0, es * (1.0 - rh_pct / 100.0))


def seasonal_rows(payload: dict, district_ru: str, district_en: str) -> list[dict]:
    params = payload["properties"]["parameter"]
    # ключи вида '202005' = год+месяц; '202013' = годовая сумма — игнорируем
    monthly: dict[tuple[int, int], dict[str, float]] = {}
    for pname, series in params.items():
        for k, v in series.items():
            if len(k) != 6 or not k.isdigit():
                continue
            y, m = int(k[:4]), int(k[4:])
            if m == 13:  # annual
                continue
            monthly.setdefault((y, m), {})[pname] = float(v)
    rows: list[dict] = []
    for year in range(START, END + 1):
        tset, xset, nset, precs, rhs, sws, wss, gws, vpds = [], [], [], [], [], [], [], [], []
        gdd = 0.0
        heat_est = 0.0
        for m in SEASON:
            rec = monthly.get((year, m))
            if rec is None:
                raise RuntimeError(f"NASA POWER: missing {year}-{m:02d} for {district_en}")
            vals = []
            for p in PARAMS.split(","):
                v = rec.get(p)
                if v is None or v <= -900:  # fill_value -999
                    raise RuntimeError(
                        f"NASA POWER fill/missing {p} {year}-{m:02d} {district_en}")
                vals.append(v)
            t, tx, tn, pr, rh, sw, ws, gw = vals
            nd = calendar.monthrange(year, m)[1]
            tset.append(t); xset.append(tx); nset.append(tn)
            precs.append(pr * nd)  # mm/day -> mm/month
            rhs.append(rh); sws.append(sw); wss.append(ws); gws.append(gw)
            gdd += max(0.0, t - 5.0) * nd
            heat_est += max(0.0, tx - 30.0) * 3.0  # эвристика, см. docstring
            vpds.append(vpd_kpa(t, rh))
        rows.append({
            "district": district_ru, "district_en": district_en, "year": year,
            "tmean_mjja": round(sum(tset) / len(tset), 2),
            "tmax_mjja": round(sum(xset) / len(xset), 2),
            "tmin_mjja": round(sum(nset) / len(nset), 2),
            "precip_mjja_sum": round(sum(precs), 1),
            "heat_days_gt30": int(round(heat_est)),
            "gdd_base5": round(gdd, 1),
            "vpd_proxy": round(sum(vpds) / len(vpds), 3),
            "rh_mjja": round(sum(rhs) / len(rhs), 1),
            "sw_mjja": round(sum(sws) / len(sws), 2),
            "ws_mjja": round(sum(wss) / len(wss), 2),
            "gwet_mjja": round(sum(gws) / len(gws), 3),
        })
    return rows


def main() -> None:
    try:
        districts = load_districts()
        RAW.mkdir(parents=True, exist_ok=True)
        all_rows: list[dict] = []
        for d in districts:
            ru, en, lat, lon = d["name_ru"], d["name_en"], d["lat"], d["lon"]
            log.info("NASA POWER %s (%s, %.2f, %.2f) ...", ru, en, lat, lon)
            payload = fetch_one(lat, lon, en)
            out_json = RAW / f"nasa_{en}.json"
            out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            log.info("  saved %s (%d bytes)", out_json.name, out_json.stat().st_size)
            rows = seasonal_rows(payload, ru, en)
            all_rows.extend(rows)
        df = pd.DataFrame(all_rows).sort_values(["district_en", "year"]).reset_index(drop=True)
        if df.empty or df.isna().any().any():
            raise ValueError(f"nasa_summary empty or has NaN:\n{df.isna().sum()}")
        df.to_csv(SUMMARY, index=False)
        log.info("WROTE %s rows=%d (districts=%d years=%d-%d)", SUMMARY, len(df),
                 df["district_en"].nunique(), df["year"].min(), df["year"].max())
    except Exception as e:
        log.exception("FATAL fetch_nasa failed (no mocks, loud fail): %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
